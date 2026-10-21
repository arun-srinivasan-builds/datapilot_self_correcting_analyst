"""Real-container security tests (PRP §6.6). Each test runs generated code in a real container."""

from __future__ import annotations

import asyncio
import json
import subprocess
import time

import pytest

from datapilot.sandbox.backend import BrokerBackend
from datapilot.sandbox.client import BrokerClient
from datapilot.sandbox.contracts import SandboxUnavailableError
from sandbox_service.broker.config import ImageLock
from sandbox_service.broker.manager import RunManager
from tests.sandbox.conftest import CSV, docker_ps_managed

pytestmark = pytest.mark.sandbox


def last_json(result: dict) -> dict:
    return json.loads(result["stdout"].strip().splitlines()[-1])


# ------------------------------------------------------------------ basic + determinism ---------
def test_run_reads_dataset_and_returns_artifacts(api):
    code = (
        "import os, json, pandas as pd\n"
        "df = pd.read_csv(os.environ['DATA_PATH'])\n"
        "print(json.dumps(df.groupby('category').units.sum().to_dict()))\n"
        "json.dump({'total': int(df.units.sum())}, open(os.environ['OUTPUT_DIR'] + '/results.json', 'w'))\n"
    )
    result = api.run_ok(code)
    assert result["status"] == "ok" and result["exit_code"] == 0
    assert last_json(result) == {"A": 7, "B": 5}
    assert [a["name"] for a in result["artifacts"]] == ["results.json"]


def test_python_error_is_reported_verbatim_with_exit_code_1(api):
    result = api.run_ok("import pandas as pd\nprint(pd.read_csv('/in/data.csv')['revenue'])\n")
    assert result["status"] == "error" and result["exit_code"] == 1
    assert "KeyError: 'revenue'" in result["stderr"] and "Traceback" in result["stderr"]


def test_identical_code_and_data_give_identical_results(api):
    code = (
        "import os, json, pandas as pd\n"
        "import matplotlib.pyplot as plt\n"
        "df = pd.read_csv(os.environ['DATA_PATH'])\n"
        "s = df.groupby('category').units.sum()\n"
        "ax = s.plot.bar(title='Units', xlabel='Category', ylabel='Units')\n"
        "ax.figure.savefig(os.environ['OUTPUT_DIR'] + '/chart.png', metadata={'Software': None})\n"
        "json.dump(s.to_dict(), open(os.environ['OUTPUT_DIR'] + '/results.json', 'w'), sort_keys=True)\n"
        "print(s.to_dict())\n"
    )
    first, second = api.run_ok(code), api.run_ok(code)
    assert first["status"] == second["status"] == "ok"
    assert first["stdout"] == second["stdout"]
    assert first["artifacts"] == second["artifacts"]  # names, sizes AND sha256 of PNG + JSON
    assert {a["name"] for a in first["artifacts"]} == {"chart.png", "results.json"}


def test_container_runs_the_pinned_python_and_package_versions(api):
    lock = ImageLock.load(api.cfg.lock_path).raw
    code = (
        "import sys, json, importlib.metadata as m\n"
        "print(json.dumps({'py': sys.version.split()[0], "
        "'pkgs': {p: m.version(p) for p in ('pandas','numpy','openpyxl','matplotlib')}}))\n"
    )
    seen = last_json(api.run_ok(code))
    assert seen["py"] == lock["python"] and seen["py"].startswith("3.11.")
    assert seen["pkgs"] == lock["packages"]


# ------------------------------------------------------------------ network + secrets -----------
def test_no_network_no_dns(api):
    code = (
        "import socket, json\n"
        "res = {}\n"
        "for host, port in (('1.1.1.1', 53), ('8.8.8.8', 443), ('93.184.216.34', 80)):\n"
        "    s = socket.socket(); s.settimeout(3)\n"
        "    try:\n"
        "        s.connect((host, port)); res[host] = 'connected'\n"
        "    except OSError as e:\n"
        "        res[host] = type(e).__name__\n"
        "try:\n"
        "    socket.gethostbyname('example.com'); res['dns'] = 'resolved'\n"
        "except OSError:\n"
        "    res['dns'] = 'failed'\n"
        "import os\n"
        "res['ifaces'] = sorted(os.listdir('/sys/class/net'))\n"
        "print(json.dumps(res))\n"
    )
    seen = last_json(api.run_ok(code))
    assert "connected" not in seen.values() and seen["dns"] == "failed"
    assert seen["ifaces"] == ["lo"]  # only loopback exists


def test_no_secrets_in_the_container_environment(api, monkeypatch):
    canaries = {
        "OPENAI_API_KEY": "sk-CANARY-should-never-appear-123456",
        "SANDBOX_TOKEN": api.token,
        "GITHUB_TOKEN": "ghp_canary-should-never-appear",
        "AWS_SECRET_ACCESS_KEY": "canary-aws-secret",
    }
    for key, value in canaries.items():
        monkeypatch.setenv(key, value)  # present in the broker's own process environment
    code = "import os, json\nprint(json.dumps(dict(os.environ)))\n"
    env = last_json(api.run_ok(code))
    for key, value in canaries.items():
        assert key not in env
        assert value not in json.dumps(env)
    allowed = {
        "DATA_PATH", "OUTPUT_DIR", "MPLBACKEND", "PYTHONHASHSEED", "TZ", "HOME", "MPLCONFIGDIR",
        "PATH", "LANG", "GPG_KEY", "PYTHON_VERSION", "PYTHON_SHA256", "HOSTNAME",
        "PIP_NO_CACHE_DIR", "PIP_DISABLE_PIP_VERSION_CHECK", "PYTHONDONTWRITEBYTECODE",  # image ENV
    }  # fmt: skip
    assert set(env) <= allowed, set(env) - allowed


def test_no_docker_socket_and_only_expected_mounts(api):
    code = (
        "import os, json\n"
        "mounts = [l.split()[:3] for l in open('/proc/mounts')]\n"
        "print(json.dumps({'sock': os.path.exists('/var/run/docker.sock') or os.path.exists('/run/docker.sock'),\n"
        "  'sock_mounts': [m for m in mounts if 'docker.sock' in ' '.join(m)],\n"
        "  'bind_like': [m[1] for m in mounts if m[1] in ('/in', '/out')],\n"
        "  'host_paths': [p for p in ('/host_mnt', '/mnt/host', '/run/desktop', '/mnt/c', '/mnt/d') if os.path.exists(p)],\n"
        "  'etc_hostname_is_container': open('/etc/hostname').read().strip() != ''}))\n"
    )
    seen = last_json(api.run_ok(code))
    assert not seen["sock"] and seen["sock_mounts"] == []
    assert sorted(seen["bind_like"]) == ["/in", "/out"]
    assert seen["host_paths"] == []


# ------------------------------------------------------------------ filesystem + identity --------
def test_filesystem_boundaries(api):
    code = (
        "import os, json, subprocess\n"
        "def tryw(path):\n"
        "    try:\n"
        "        open(path, 'w').write('x'); return 'wrote'\n"
        "    except OSError as e:\n"
        "        return type(e).__name__ + ':' + str(e.errno)\n"
        "r = {'in': tryw('/in/evil.txt'), 'in_overwrite': tryw('/in/analysis.py'), 'root': tryw('/evil.txt'),\n"
        "     'etc': tryw('/etc/evil'), 'out': tryw('/out/ok.txt'), 'tmp': tryw('/tmp/ok.txt')}\n"
        "open('/tmp/run.sh', 'w').write('#!/bin/sh\\necho pwned\\n'); os.chmod('/tmp/run.sh', 0o755)\n"
        "try:\n"
        "    subprocess.run(['/tmp/run.sh'], check=True, capture_output=True); r['tmp_exec'] = 'executed'\n"
        "except Exception as e:\n"
        "    r['tmp_exec'] = type(e).__name__\n"
        "r['in_listing'] = sorted(os.listdir('/in'))\n"
        "r['secrets_visible'] = [p for p in ('/root', '/home', '/app', '/proc/1/environ') if os.path.exists(p) and os.access(p, os.R_OK) and p != '/proc/1/environ']\n"
        "print(json.dumps(r))\n"
    )
    seen = last_json(api.run_ok(code))
    for denied in ("in", "in_overwrite", "root", "etc"):
        assert seen[denied].startswith("OSError") or seen[denied].split(":")[0].endswith("Error"), (
            denied,
            seen[denied],
        )
        assert seen[denied] != "wrote"
    assert seen["out"] == "wrote" and seen["tmp"] == "wrote"
    assert seen["tmp_exec"] != "executed"  # /tmp is noexec
    assert seen["in_listing"] == ["analysis.py", "data.csv"]


def test_runs_as_non_root_without_capabilities_and_no_new_privileges(api):
    code = (
        "import os, json\n"
        "status = dict(l.split(':\\t', 1) for l in open('/proc/self/status').read().splitlines() if ':\\t' in l)\n"
        "print(json.dumps({'uid': os.getuid(), 'gid': os.getgid(), 'cap_eff': status['CapEff'].strip(),\n"
        " 'cap_bnd': status['CapBnd'].strip(), 'nnp': status['NoNewPrivs'].strip()}))\n"
    )
    seen = last_json(api.run_ok(code))
    assert seen["uid"] == 10001 and seen["gid"] == 10001
    assert set(seen["cap_eff"]) == {"0"} and set(seen["cap_bnd"]) == {"0"}
    assert seen["nnp"] == "1"


def test_one_run_cannot_see_another_runs_files(api):
    marker = "SECRET-FROM-RUN-ONE"
    api.run_ok(
        f"open('/tmp/leak.txt','w').write('{marker}'); open('/out/leak.txt','w').write('{marker}')"
    )
    seen = last_json(
        api.run_ok(
            "import os, json\n"
            "print(json.dumps({'tmp': os.path.exists('/tmp/leak.txt'), 'out': os.listdir('/out')}))\n"
        )
    )
    assert seen == {"tmp": False, "out": []}


# ------------------------------------------------------------------ resource limits -------------
def test_infinite_loop_is_killed_as_timeout(api):
    started = time.monotonic()
    result = api.run_ok("while True:\n    pass\n", timeout_s=3)
    assert result["status"] == "timeout" and result["exit_code"] == 124
    assert time.monotonic() - started < 25
    assert "wall-clock" in result["stderr"]


def test_memory_hog_is_oom_killed(api):
    result = api.run_ok(
        "blocks = []\nwhile True:\n    blocks.append(b'x' * (50 * 1024 * 1024))\n", timeout_s=40
    )
    assert result["status"] == "killed" and result["exit_code"] == 137
    assert "out of memory" in result["stderr"]


def test_fork_bomb_is_bounded_by_the_pids_limit(api):
    code = (
        "import os, time, json\n"
        "n, err = 0, None\n"
        "try:\n"
        "    for _ in range(2000):\n"
        "        pid = os.fork()\n"
        "        if pid == 0:\n"
        "            time.sleep(8); os._exit(0)\n"
        "        n += 1\n"
        "except OSError as e:\n"
        "    err = type(e).__name__\n"
        "print(json.dumps({'forked': n, 'error': err}), flush=True)\n"
        "os._exit(0)\n"
    )
    seen = last_json(api.run_ok(code, timeout_s=30))
    assert seen["error"] is not None and seen["forked"] < 128


def test_output_flood_is_truncated(api):
    result = api.run_ok("for _ in range(300):\n    print('x' * 100_000)\n", timeout_s=30)
    assert result["truncated"] is True
    assert len(result["stdout"]) <= api.cfg.output_cap_bytes


def test_disk_fill_in_output_dir_is_stopped(api):
    code = (
        "import time\n"
        "for i in range(40):\n"
        "    with open(f'/out/f{i}.csv', 'wb') as f:\n"
        "        f.write(b'x' * (3 * 1024 * 1024))\n"
        "    time.sleep(0.1)\n"
    )
    result = api.run_ok(code, timeout_s=40)
    assert result["status"] == "killed" and "output size limit" in result["stderr"]


def test_single_huge_file_cannot_be_written(api):
    code = (
        "try:\n"
        "    with open('/out/big.csv', 'wb') as f:\n"
        "        f.write(b'x' * (200 * 1024 * 1024))\n"
        "    print('wrote')\n"
        "except OSError as e:\n"
        "    print('blocked', e.errno)\n"
    )
    result = api.run_ok(code, timeout_s=40)
    assert "big.csv" not in [a["name"] for a in result["artifacts"]]  # never collected (>5 MB cap)


# ------------------------------------------------------------------ artifact collection ---------
def test_unsafe_outputs_are_rejected_not_collected(api):
    code = (
        "import os\n"
        "out = '/out/'\n"
        "open(out + 'results.json', 'w').write('{}')\n"
        "open(out + 'chart.png', 'wb').write(b'\\x89PNG')\n"
        "os.mkdir(out + 'sub'); open(out + 'sub/inner.txt', 'w').write('x')\n"
        "open(out + 'run.sh', 'w').write('echo x')\n"
        "open(out + 'bad name!.txt', 'w').write('x')\n"
        "open(out + 'big.csv', 'wb').write(b'x' * (6 * 1024 * 1024))\n"
        "for target, name in (('/in/data.csv', 'link_in.txt'), ('/etc/passwd', 'link_etc.txt')):\n"
        "    try:\n"
        "        os.symlink(target, out + name)\n"
        "    except OSError:\n"
        "        pass\n"
    )
    result = api.run_ok(code)
    names = {a["name"] for a in result["artifacts"]}
    assert names == {"results.json", "chart.png"}
    reasons = {r["reason"] for r in result["rejected_artifacts"]}
    assert {"directory", "name_or_extension_not_allowed", "file_too_large"} <= reasons
    assert not any("passwd" in str(r) or "root:" in str(r) for r in result["rejected_artifacts"])


def test_artifact_download_and_delete(api):
    status, body = api.run("open('/out/results.json','w').write('{\"a\": 1}')")
    assert status == 200
    exec_id = body["exec_id"]
    status, data = api.call("GET", f"/v1/runs/{exec_id}/artifacts/results.json")
    assert status == 200 and data == {"a": 1}
    assert (api.manager.layout.artifact_dir(exec_id) / "results.json").is_file()
    assert api.call("DELETE", f"/v1/runs/{exec_id}")[0] == 200
    assert not api.manager.layout.artifact_dir(exec_id).exists()
    assert api.call("GET", f"/v1/runs/{exec_id}/artifacts/results.json")[0] == 404


# ------------------------------------------------------------------ live container config -------
def test_live_container_has_exactly_the_approved_configuration(api, engine):
    run = api.background("import time\ntime.sleep(60)\n", timeout_s=90)
    name = run.wait_for_container()
    info = json.loads(
        subprocess.run(  # noqa: S603
            ["docker", "inspect", name], capture_output=True, text=True, timeout=60, check=True
        ).stdout
    )[0]
    host, config = info["HostConfig"], info["Config"]
    lock = ImageLock.load(api.cfg.lock_path)
    assert host["NetworkMode"] == "none"
    assert host["ReadonlyRootfs"] is True and host["Privileged"] is False
    assert [c.upper() for c in host["CapDrop"]] == ["ALL"] and not host["CapAdd"]
    assert "no-new-privileges" in " ".join(host["SecurityOpt"])
    assert host["Memory"] == 512 * 1024 * 1024 and host["MemorySwap"] == host["Memory"]
    assert host["PidsLimit"] == 128 and host["NanoCpus"] == 1_000_000_000
    assert host["PortBindings"] in ({}, None) and not host["Devices"] and not host["Binds"]
    assert host["PidMode"] == "" and host["IpcMode"] != "host" and host["UsernsMode"] == ""
    assert config["User"] == "10001:10001"
    assert config["Cmd"] == ["python", "-I", "/in/analysis.py"]
    assert info["Image"] == lock.image_id
    mounts = {m["Destination"]: m for m in info["Mounts"]}
    assert set(mounts) == {"/in", "/out"} and all(m["Type"] == "bind" for m in mounts.values())
    assert mounts["/in"]["RW"] is False and mounts["/out"]["RW"] is True
    assert "/var/run/docker.sock" not in json.dumps(info["Mounts"])
    assert not any(
        "TOKEN" in e or "OPENAI" in e or "KEY=" in e.replace("GPG_KEY", "") for e in config["Env"]
    )
    assert config["Labels"]["datapilot.sandbox"] == "1"
    api.call("DELETE", f"/v1/runs/{run.exec_id}")
    status, body = run.join()
    assert status == 200 and body["status"] == "killed"


# ------------------------------------------------------------------ cancellation + cleanup ------
def test_delete_cancels_a_running_execution_and_removes_the_container(api):
    run = api.background("import time\ntime.sleep(120)\n", timeout_s=120)
    name = run.wait_for_container()
    started = time.monotonic()
    assert api.call("DELETE", f"/v1/runs/{run.exec_id}")[0] == 200
    status, body = run.join(timeout=30)
    assert status == 200 and body["status"] == "killed" and "cancelled" in body["stderr"]
    assert time.monotonic() - started < 15
    assert name not in docker_ps_managed()


async def test_backend_cancellation_kills_the_container(api):
    backend = BrokerBackend(
        BrokerClient(f"http://127.0.0.1:{api.server.port}", api.token), CSV, "csv", timeout_s=120
    )
    task = asyncio.create_task(backend.run("import time\ntime.sleep(120)\n", run_id="r1"))
    deadline = time.monotonic() + 30
    while not docker_ps_managed() and time.monotonic() < deadline:
        await asyncio.sleep(0.2)
    assert docker_ps_managed(), "container never started"
    await asyncio.sleep(1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    deadline = time.monotonic() + 20
    while docker_ps_managed() and time.monotonic() < deadline:
        await asyncio.sleep(0.2)
    assert docker_ps_managed() == []


async def test_backend_returns_a_structured_result_and_reports_unreachable_broker(api):
    backend = BrokerBackend(
        BrokerClient(f"http://127.0.0.1:{api.server.port}", api.token), CSV, "csv", timeout_s=30
    )
    result = await backend.run(
        "print('hi')\nopen('/out/results.json','w').write('{}')", run_id="r2"
    )
    assert result.ok and result.stdout == "hi\n" and result.artifacts[0].name == "results.json"
    assert await backend.fetch_artifact(result, "results.json") == b"{}"
    await backend.release(result)
    down = BrokerBackend(BrokerClient("http://127.0.0.1:9", api.token), CSV, "csv")
    with pytest.raises(SandboxUnavailableError):
        await down.run("print(1)", run_id="r3")
    wrong = BrokerBackend(BrokerClient(f"http://127.0.0.1:{api.server.port}", "w" * 40), CSV, "csv")
    with pytest.raises(SandboxUnavailableError, match="credentials"):
        await wrong.run("print(1)", run_id="r4")


def test_broker_restart_reaps_orphaned_containers_and_directories(api, engine):
    lock = ImageLock.load(api.cfg.lock_path)
    stray = f"{api.cfg.container_prefix}orphan000001"
    subprocess.run(  # noqa: S603 - a container a crashed broker would have left running
        ["docker", "run", "-d", "--name", stray, "--label", "datapilot.sandbox=1", "--network", "none",
         lock.image_id, "python", "-c", "import time; time.sleep(300)"],
        capture_output=True, check=True, timeout=60,
    )  # fmt: skip
    (api.manager.layout.runs / "orphan000001" / "in").mkdir(parents=True)
    assert stray in docker_ps_managed()
    fresh = RunManager(api.cfg, engine, lock)  # what a restarted broker constructs
    removed = fresh.startup_reap()
    assert stray in removed["containers"] and "runs/orphan000001" in removed["directories"]
    assert docker_ps_managed() == [] and list(api.manager.layout.runs.iterdir()) == []


def test_restart_during_a_live_run_leaves_nothing_behind(api, engine):
    run = api.background("import time\ntime.sleep(120)\n", timeout_s=120)
    run.wait_for_container()
    fresh = RunManager(api.cfg, engine, ImageLock.load(api.cfg.lock_path))
    fresh.startup_reap()  # a restarted broker removes the predecessor's container + directory
    status, body = run.join(timeout=30)  # the original handler unwinds and cleans up too
    assert status == 200 and body["status"] in ("error", "killed")
    assert docker_ps_managed() == []


def test_cleanup_after_success_error_timeout_and_oom_leaves_no_trace(api):
    api.run_ok("print(1)")
    api.run_ok("raise SystemExit(3)")
    api.run_ok("while True: pass", timeout_s=2)
    api.run_ok("b=[]\nwhile True: b.append(b'x'*(50*1024*1024))", timeout_s=40)
    assert docker_ps_managed() == []
    assert list(api.manager.layout.runs.iterdir()) == []
    assert list(api.manager.layout.artifacts.iterdir()) == []


def test_concurrency_limit_returns_429_not_unbounded_containers(api):
    runs = [
        api.background("import time\ntime.sleep(60)\n", timeout_s=90)
        for _ in range(api.cfg.max_concurrent)
    ]
    for run in runs:
        run.wait_for_container()
    status, body = api.run("print(1)")
    assert status == 429 and body["error"] == "busy"
    for run in runs:
        api.call("DELETE", f"/v1/runs/{run.exec_id}")
        run.join(timeout=30)


def test_runs_without_artifacts_leave_no_directory_even_if_never_deleted(api):
    status, body = api.run("print('no files written')")
    assert status == 200 and body["artifacts"] == []
    assert not api.manager.layout.artifact_dir(body["exec_id"]).exists()
    assert list(api.manager.layout.artifacts.iterdir()) == []
