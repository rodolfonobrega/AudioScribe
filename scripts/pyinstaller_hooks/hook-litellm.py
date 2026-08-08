"""Keep LiteLLM runtime data while avoiding a duplicate tokenizer payload."""

from PyInstaller.utils.hooks import collect_data_files


datas = [
    (source, destination)
    for source, destination in collect_data_files("litellm")
    if "litellm_core_utils\\tokenizers" not in source.replace("/", "\\")
]
