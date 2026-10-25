"""Off-machine backup acknowledgment for automatic GPU shutdown."""
import subprocess,sys,time,json,hashlib,tarfile
from pathlib import Path
base=Path(sys.argv[1]);base.mkdir(parents=True,exist_ok=True)
host='root@connect.nmb1.seetacloud.com';ssh=['ssh','-o','ConnectTimeout=10','-p','15559',host];remote='/root/autodl-tmp/registered-20261024'
while True:
 p=subprocess.run(ssh+['cat '+remote+'/archive_ready.json'],capture_output=True,text=True)
 if p.returncode==0:
  receipt=json.loads(p.stdout);break
 time.sleep(20)
archive=base/'registered-20261024-results.tar.gz'
for attempt in range(10):
 p=subprocess.run(['scp','-o','ConnectTimeout=10','-P','15559',host+':'+receipt['archive'],str(archive)],capture_output=True,text=True)
 if p.returncode==0 and hashlib.sha256(archive.read_bytes()).hexdigest()==receipt['sha256']:break
 time.sleep(5)
else:raise RuntimeError('Remote archive could not be copied and verified')
with tarfile.open(archive,'r:gz') as t:
 for member in t.getmembers():
  if member.name.startswith('/') or '..' in Path(member.name).parts or member.issym() or member.islnk():raise ValueError('Unsafe archive member')
 t.extractall(base)
folder=base/'registered-20261024';manifest=json.loads((folder/'file_sha256.json').read_text())
for name,digest in manifest.items():assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest,name
ack={'sha256':receipt['sha256'],'local_archive':str(archive),'verified_files':len(manifest),'epoch':time.time()}
(base/'backup_receipt.json').write_text(json.dumps(ack,indent=2));subprocess.run(ssh+['cat > '+remote+'/off_machine_backup_ack.json'],input=json.dumps(ack),text=True,check=True)
for _ in range(10):
 p=subprocess.run(ssh+['cat '+remote+'/shutdown_receipt.json'],capture_output=True,text=True)
 if p.returncode==0:
  (base/'shutdown_receipt.json').write_text(p.stdout)
  if json.loads(p.stdout).get('status')=='platform_supervisor_shutdown':break
 time.sleep(1)
print(json.dumps(ack),flush=True)
