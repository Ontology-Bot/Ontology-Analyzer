from pathlib import Path

from app.repo.snapshot import Snapshot
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
        
    def is_empty(self):
        return self.repo_id is None or self.get_at_head() is None

    def _save_result(self, snapshot: Snapshot, update_head: bool = True):
        # save snapshot to new folder with timestamp
        timestamp = snapshot.timestamp.strftime("%Y%m%d_%H%M%S")
        folder_path = self.path / timestamp
        folder_path.mkdir(exist_ok=True)
        result_path = folder_path / "snapshot.json"
        logger.info(f"Saving snapshot {timestamp}")
        write_json(result_path, snapshot.model_dump(mode="json"))
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

    def drop(self):
        # delete all folders and files
        for item in self.path.iterdir():
            if item.is_dir():
                for subitem in item.iterdir():
                    subitem.unlink()
                item.rmdir()
            else:
                item.unlink()
        self.repo_id = None
        logger.info("Repository cleared.")

    def drop_at_timestamp(self, timestamp: str):
        # delete folder for specific timestamp
        folder_path = self.path / timestamp
        if folder_path.exists():
            for subitem in folder_path.iterdir():
                subitem.unlink()
            folder_path.rmdir()
            logger.info(f"Deleted results for timestamp '{timestamp}'")
        else:
            logger.info("Invalid timestamp.")

    def commit(self, snapshot: Snapshot):
        # check repo_id
        if self.repo_id is None: # first time loading dataset, set repo_id
            logger.info(f"Initial commit. Setting repository id to '{snapshot.repo_id}'")
            self.repo_id = snapshot.repo_id
            write_json(self.meta_path, {"repo_id": self.repo_id})
        if self.repo_id != snapshot.repo_id:
            # TODO 
            raise ValueError(f"Dataset repo_id '{snapshot.repo_id}' does not match repository meta repo_id '{self.repo_id}'. Choose another dataset or repository path.")

        # save snapshot to new folder with timestamp
        self._save_result(snapshot, update_head=True)