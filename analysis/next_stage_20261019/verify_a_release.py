"""Run unchanged A c77e91c CLIs in a byte-identical disposable sandbox.
Reproduce: $PY analysis/next_stage_20261019/verify_a_release.py --a-repo <A_REPO> --out <NEW_OUT>
A writes reports, so never invoke its output-producing CLIs in its read-only tree.
"""
import argparse,hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path
A_COMMIT='c77e91c07a288b719683c51258324c11431c12d5'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def inventory(a):
 names=subprocess.check_output(['git','ls-files','-z','a-side'],cwd=a).decode().split('\0')
 return {n:sha(a/n) for n in names if n and (a/n).is_file()}
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def run(a,out):
 a,out=Path(a).resolve(),Path(out).resolve()
 if out.exists() or out.is_relative_to(a):raise ValueError('New output outside A required')
 commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=a).decode().strip()
 if commit!=A_COMMIT:raise ValueError('Expected pinned A c77e91c')
 before=inventory(a);out.mkdir(parents=True);calls=[];checks={}
 with tempfile.TemporaryDirectory(prefix='B-native-A-') as tmp:
  native=Path(tmp);shutil.copytree(a/'a-side',native/'a-side',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
  for n,pin in before.items():
   if sha(native/n)!=pin:raise ValueError('Native snapshot differs: '+n)
  env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'};env.pop('EDGECORAG_IFACE',None)
  commands=[('a17_default',['a-side/scripts/a17_verify_interface.py']),
   ('a17_strict',['a-side/scripts/a17_verify_interface.py','--strict-lf']),
   ('a20_example',['a-side/scripts/a20_validate_index_receipt.py','a-side/contracts/index_receipt.example.json']),
   ('a22',['a-side/scripts/a22_crlf_guard_test.py'])]
  for label,args in commands:
   r=subprocess.run(['python3',*args],cwd=native,env=env,capture_output=True,text=True)
   calls.append(dict(label=label,command=['python3',*args],returncode=r.returncode))
   (out/(label+'.txt')).write_text((r.stdout+r.stderr).replace(str(native),'<NATIVE_A>'))
   if label.startswith('a17'):
    value=json.loads((native/'a-side/retrieval_if_v1/verify.json').read_text())
    write(out/(label+'.json'),value);checks[label]={k:value[k] for k in ('artifacts_checked','fail_count','files_with_crlf','hash_normalization')}
   elif label=='a20_example':checks[label]=json.loads(r.stdout)
   else:checks[label]=json.JSONDecoder().raw_decode(r.stdout.strip())[0]
  if inventory(a)!=before:raise ValueError('A changed externally; stop and report')
 result=dict(A_commit=commit,commands=calls,checks=checks,
  artifact_manifest_sha256=sha(a/'a-side/retrieval_if_v1/artifacts.json'),
  A_tracked_files=len(before),A_unchanged=True,source_sha256=before,
  invocation_scope='Unmodified native CLIs on byte-identical B sandbox snapshot; source A remains read-only',
  B1_passed=all(c['returncode']==0 for c in calls) and checks['a17_default']['artifacts_checked']==36 and checks['a17_default']['fail_count']==0 and checks['a22']['passed']==checks['a22']['total']==8)
 write(out/'G1_release_check.json',result)
 print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'},ensure_ascii=False,indent=2))
 return 0 if result['B1_passed'] else 1
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--a-repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();return run(a.a_repo,a.out)
if __name__=='__main__':raise SystemExit(main())
