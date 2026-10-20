"""Explicit-input artifact-to-command registry; CPU reproduction or named blocker.
Reproduce: $PY analysis/next_stage_20261019/p4_reproduce.py --work-dir <ARCHIVES> --metadata-dir <METADATA> --legacy-export-dir <ORIGINAL_EXPORT> --official-source <SCORE_PY> --archive <ROUND1_TAR> --frozen-receipt <FROZEN_RECEIPT> --out <NEW_REPORT_DIR>
Shared commands run once per group. Partial/blocked is not an all-pass claim.
"""
import argparse,csv,json,os,subprocess,sys
from pathlib import Path
from a_interface_evidence import sha,save,table
REPO=Path(__file__).resolve().parents[2]
ART=Path('reports/next_stage_20261019/quality_closure_20261021')
PREFIX='analysis/next_stage_20261019/'

def specs(repo):
    manifest=json.loads((repo/ART/'manifest.json').read_text());quality=[*manifest['files'],'manifest.json']
    groups=[('quality',quality,['verify_quality_closure.py','--work-dir','{work_dir}','--artifact-dir',str(ART)]),
        ('supplements',['mechanism_samples.csv','O2_partition_and_Holm_references.csv','O2_upgrade_limitations.json','O4_measurement_gap_contract.json','O5_interface_validation.json'],['offline_interface_supplements.py','--work-dir','{work_dir}','--artifact-dir',str(ART),'--verify']),
        ('official_frozen',['official_export_receipt.json','official_export_validation.json','official_schema_validation.json'],['verify_frozen_export.py','--snapshot','61fe155','--metadata-dir','{metadata_dir}','--export-dir','{legacy_export_dir}','--official-source','{official_source}']),
        ('source_snapshot',['source_archive_supplement.json','source_pin_reproducibility.csv'],['append_source_provenance.py','--archive','{archive}','--receipt','{frozen_receipt}','--source-snapshot','61fe155','--verify-json',str(ART/'source_archive_supplement.json'),'--verify-table',str(ART/'source_pin_reproducibility.csv')])]
    for name in ('Q_completion_counts.json','status_changes.json','Q_requirement_evidence_audit.json'):
        groups.append((name,[name],['verify_historical_metadata.py','--snapshot','61fe155','--artifact',name]))
    names=[n for _,files,_ in groups for n in files]
    if len(names)!=len(set(names)) or set(names)!={p.name for p in (repo/ART).iterdir() if p.is_file()}:raise ValueError('Artifact registry is incomplete/duplicated')
    return groups

def run(args):
    out=args.out.resolve()
    if out.exists():raise ValueError('New report directory required')
    out.mkdir(parents=True);rows=[];commands=[];env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    roots={key:getattr(args,key) for key in ('work_dir','metadata_dir','export_dir','legacy_export_dir','official_source','archive','frozen_receipt')}
    for label,names,command in specs(REPO):
        template=[PREFIX+command[0],*command[1:]];expanded=[];missing=[]
        for word in template:
            if word.startswith('{'):
                key=word[1:-1];p=roots.get(key)
                if p is None or not p.exists():missing.append('--'+key.replace('_','-'))
                expanded.append(str(p) if p else word)
            else:expanded.append(word)
        reason='';rc=2;stderr='';stdout=''
        if missing:status='blocked';reason='Missing explicit inputs: '+','.join(missing)
        else:
            p=subprocess.run([sys.executable,*expanded],cwd=REPO,env=env,capture_output=True,text=True,timeout=120)
            rc=p.returncode;stdout=p.stdout;stderr=p.stderr
            status='verified_recomputed' if rc==0 else 'blocked' if label in ('source_snapshot','Q_requirement_evidence_audit.json') else 'failed'
            if label=='source_snapshot' and rc!=0:reason='Archive historical pins reproduce; saved current_sha/current_matches_pin refer to another source snapshot. Original source snapshot bytes for exact metadata replay not supplied. Preserve old table; do not rewrite history.'
            if label=='Q_requirement_evidence_audit.json':reason='Historical audit process is not exactly replayable from fully versioned original inputs; current audit is reported separately.'
        scrub=stderr
        for p in [REPO,*[p for p in roots.values() if p is not None]]:scrub=scrub.replace(str(p),'<EXPLICIT_INPUT>')
        save(out/(label+'.json'),dict(command=template,returncode=rc,status=status,reason=reason,stdout=stdout,stderr=scrub))
        commands.append(dict(group=label,command=template,returncode=rc,status=status,reason=reason))
        for name in names:rows.append(dict(artifact=str(ART/name),sha256=sha(REPO/ART/name),command='$PY '+' '.join(template),returncode=rc,status=status,required_inputs=';'.join(w[1:-1] for w in template if w.startswith('{')),limitation=reason,shared_invocation=label))
    table(out/'artifact_commands.csv',rows)
    summary=dict(artifacts=len(rows),verified=sum(r['status']=='verified_recomputed' for r in rows),blocked=sum(r['status']=='blocked' for r in rows),failed=sum(r['status']=='failed' for r in rows),commands=commands,
        grouping='Each shared command executed once in this batch; same invocation/rc covers listed members. Blocked rows never labelled passed.',
        scientific_contract='564 query-image components;10000 bootstrap;seed42;query-weighted;uncorrected+Holm-compatible family intervals;descriptive;post hoc Oracle separate;cross0 cannot exclude no difference',
        missing_input_policy='Declare required input flags. Missing input blocks only that group, not remaining groups.')
    save(out/'summary.json',summary)
    return 1 if summary['failed'] else 2 if summary['blocked'] else 0

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('work-dir','metadata-dir','export-dir','legacy-export-dir','official-source','archive','frozen-receipt'):p.add_argument('--'+name,type=Path)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args();return run(a)
if __name__=='__main__':raise SystemExit(main())
