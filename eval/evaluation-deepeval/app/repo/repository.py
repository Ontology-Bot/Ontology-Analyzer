
from curses import meta
from pathlib import Path

from app.repo.snapshot import Snapshot, EvaluatedTestResult
from app.repo.helpers import read_json, write_json


import logging
logger = logging.getLogger(__name__)

class Repository:
    '''
    File structure:
    repo/
        meta.json # has repo name
        head.json
        <timestamp>/
            snapshot.json
            dataset.json # filled with output TODO
            result.json # TODO

    '''
    def __init__(self, path: Path):
        # create directory if not exists
        self.path = path
        self.path.mkdir(exist_ok=True, parents=True)
        self.head_path = self.path / "head.json"
        self.meta_path = self.path / "meta.json"
        # try load repo id
        self.repo_id: str | None = None
        if self.meta_path.exists():
            meta = read_json(self.meta_path)
            self.repo_id = meta.get("repo_id", None)
        else:
            logger.info("Empty repository was loaded.")
            

    def load_dataset(self, path: Path):
        # create snapshot from dataset file
        snapshot = Snapshot.from_dataset(read_json(path))
        # check repo_id
        if self.repo_id is None: # first time loading dataset, set repo_id
            logger.info(f"Setting repository id to '{snapshot.repo_id}'")
            self.repo_id = snapshot.repo_id
            write_json(self.meta_path, {"repo_id": self.repo_id})
        if self.repo_id != snapshot.repo_id:
            # TODO 
            raise ValueError(f"Dataset repo_id '{snapshot.repo_id}' does not match repository meta repo_id '{self.repo_id}'. Choose another dataset or repository path.")
        # load head if exists
        head = self.get_at_head()
        if head is not None:
            logger.info("Merging dataset with head.")
            # merge snapshot with head
            snapshot = Snapshot.merge(head, snapshot)
        # save snapshot and update head
        self._save_result(snapshot, update_head=True)

    def _save_result(self, snapshot: Snapshot, update_head: bool = True):
        # save snapshot to new folder with timestamp
        timestamp = snapshot.timestamp.isoformat()
        folder_path = self.path / timestamp
        folder_path.mkdir(exist_ok=True)
        result_path = folder_path / "snapshot.json"
        logger.info(f"Saving snapshot {timestamp}")
        write_json(result_path, snapshot.model_dump())
        if update_head:
            logger.info(f"Updated head {timestamp}")
            write_json(self.head_path, {"timestamp": timestamp})


    def list(self):
        # get all folder names
        return sorted([d.name for d in self.path.iterdir() if d.is_dir()], reverse=True)
        
    def get_at_head(self) -> Snapshot | None:
        if self.head_path.exists():
            timestamp = read_json(self.head_path).get("timestamp", None)
            if timestamp is not None:
                return self.get_at_timestamp(timestamp)
            else:
                logger.warning("Invalid head timestamp.")
        logger.info("Empty repository or head not found.")
        return None
    
    def get_at_timestamp(self, timestamp: str) -> Snapshot | None:
        path = self.path / timestamp / "snapshot.json"
        if not path.exists():
            logger.info("Invalid timestamp.")
            return None
        return Snapshot.model_validate(read_json(path))

    #def begin_evaluation(self, tests: list[str] | None, judge: str, model: str, metrics: list[str], invalidate_cache: bool = False) -> Snapshot:
        # create new snapshot with status "running"
        #return Snapshot.from_testlist(self.get_at_head(), tests, judge, model, metrics, invalidate_cache)

    def commit(self, snapshot: Snapshot):
        # save snapshot to new folder with timestamp
        self._save_result(snapshot, update_head=True)