"""Install the narrow ONNX publisher without restarting active GPU workers."""

import shlex
import subprocess

REMOTE = """import pathlib,shlex,subprocess
root=pathlib.Path.home()/'robot-training-hub'
worker=pathlib.Path.home()/'.config/systemd/user/robot-training-hub-worker.service'
line=next(line for line in worker.read_text().splitlines() if line.startswith('ExecStart='))
args=shlex.split(line.split('=',1)[1]);index=args.index('hub.worker');args[index]='hub.policy_sync'
unit=worker.with_name('robot-training-hub-policy-sync.service')
unit.write_text('[Unit]\\nDescription=Robot Training Hub ONNX policy publisher\\nAfter=network-online.target\\n\\n[Service]\\nType=simple\\nWorkingDirectory='+str(root)+'\\nEnvironment=OMP_NUM_THREADS=1\\nExecStart='+shlex.join(args)+'\\nRestart=on-failure\\nRestartSec=10\\nUMask=0077\\n\\n[Install]\\nWantedBy=default.target\\n')
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
state=subprocess.check_output(['systemctl','--user','show','-p','LoadState','--value',unit.name],text=True).strip()
if state=='not-found':
 subprocess.run(['systemctl','--user','link','--runtime',str(unit)],check=True)
 subprocess.run(['systemctl','--user','daemon-reload'],check=True)
 subprocess.run(['systemctl','--user','enable','--runtime','--now',unit.name],check=True)
else:
 subprocess.run(['systemctl','--user','enable','--now',unit.name],check=True)
subprocess.run(['systemctl','--user','is-active',unit.name],check=True)
"""
for host in ["operator@192.0.2.20", "worker-a.example.edu", "worker-b.example.edu"]:
    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", host, "python3 -c " + shlex.quote(REMOTE)],
        check=True,
    )
    print(host + ": ONNX publisher installed; GPU worker preserved")
