"""Run an actual stateful simulation example in a spawned worker, without Qt GUI."""
import argparse
import json
import multiprocessing
from pathlib import Path
import tempfile
import time

from app.automation.runtime import RuntimeCoordinator
from app.simulation.model import LABEL, SCENARIOS, SimulationManager
from app.simulation.project import create_project, SOURCES


def main():
    multiprocessing.freeze_support()
    parser=argparse.ArgumentParser(description=LABEL)
    parser.add_argument('--scenario',choices=SCENARIOS,default='image')
    parser.add_argument('--delay',type=float,default=1)
    args=parser.parse_args()
    manager=SimulationManager()
    try:
        with tempfile.TemporaryDirectory(prefix='aas-demo-project-') as directory:
            info=manager.create(args.scenario,args.delay)
            project,script=create_project(Path(directory),info.serial,args.scenario)
            print(LABEL,flush=True)
            # This command explicitly executes its own bundled example only.
            # The desktop still requests source approval for user scripts.
            with RuntimeCoordinator() as runtime:
                run=runtime.start(SOURCES[args.scenario],info.serial,backend='simulation',trusted=True,
                                  project_root=project,script_id=str(script),simulation_config=manager.config(info.serial))
                while True:
                    for event in runtime.poll():
                        if event['event'] in ('output','error'):
                            print(json.dumps(event,ensure_ascii=False),flush=True)
                    state=next(item for item in runtime.snapshot() if item.run_id==run)
                    if state.exitcode is not None:
                        print(json.dumps({'worker_state':state.state,'simulation_screen':manager.client(info.serial).state()['screen']}))
                        return 0 if state.state=='completed' else 1
                    time.sleep(.01)
    finally:manager.close()


if __name__=='__main__':raise SystemExit(main())
