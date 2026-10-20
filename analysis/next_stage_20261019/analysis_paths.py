"""Portable path arguments shared by the archived local analysis entry points.

No inputs are opened here. A caller must supply private input roots separately;
--help is safe on a fresh checkout. Paths describe layout, never authorization.
"""
import argparse
from pathlib import Path
import sys


def settings(module_name, description, own_parser=False):
    parser=argparse.ArgumentParser(description=description, add_help=not own_parser)
    parser.add_argument('--project-root',type=Path,default=Path.cwd(),help='private data layout root')
    parser.add_argument('--work-dir',type=Path,help='private work inputs')
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output-dir',type=Path,help='new output directory (never an archive input)')
    parser.add_argument('--archive-root',type=Path,help='verified retrieval backup directory')
    parser.add_argument('--legacy-root',type=Path,help='verified legacy backup for historical scorer')
    parser.add_argument('--run-id',default='new-session',help='fresh output namespace, never an existing run')
    parser.add_argument('--dimension-inputs',type=Path,help='explicit new private development input directory')
    parser.add_argument('--interface-freeze',type=Path,help='explicit new interface freeze JSON')
    parser.add_argument('--server-root',type=Path,help='intended remote data root; preparation only')
    args, remaining=parser.parse_known_args() if module_name=='__main__' else parser.parse_known_args([])
    if module_name=='__main__':
        if own_parser and '--help' in remaining:
            parser.print_help()
        sys.argv[1:]=remaining
    args.project_root=args.project_root.resolve()
    args.repo=args.repo.resolve()
    args.work_dir=(args.work_dir or args.project_root/'work/next-experiment-20261019').resolve()
    args.archive_root=(args.archive_root or args.project_root/'work/instance394-preflight/formal-retrieval-embeddinggemma2-backup').resolve()
    return args
