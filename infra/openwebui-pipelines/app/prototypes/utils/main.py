from typing import List, Literal, TypeAlias
import os

Role: TypeAlias = Literal["user", "assistant"] # type Role = "user" | "assistant"

def get_last_message(role: Role, messages: List[dict]) -> str:
    for message in reversed(messages):
        if message["role"] == role:
            if isinstance(message["content"], list):
                for item in message["content"]:
                    if item["type"] == "text":
                        return item["text"]
            return message["content"] # type: ignore
    return None # type: ignore
    
    
def set_last_message(role: Role, messages: List[dict], msg: str):
    for message in reversed(messages):
        if message["role"] == role:
            if isinstance(message["content"], list):
                for item in message["content"]:
                    if item["type"] == "text":
                        item["text"] = msg
                        return
            message["content"] = msg
            return 


def get_system_message(messages: List[dict]) -> dict:
    for message in messages:
        if message["role"] == "system":
            return message
    return None # type: ignore


def get_cache_path() -> str:
    # this is temporal logic, idk how to make it better
    cur_folder = os.path.basename(os.getcwd())

    # Check if it is "app"
    if cur_folder != "app":
        raise RuntimeError(f"Expected to be in 'app' folder, but current folder is '{cur_folder}'.")

    path = "./data/"
    os.makedirs(path, exist_ok=True)
    return path