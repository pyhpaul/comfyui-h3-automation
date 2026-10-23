"""Feiniu archive keeps the four delivery files and skips local extras."""

from comfy_orch.feiniu_archive import archive_named_files, remote_unit_dir, select_archive_files


class _Item:
    def __init__(self, name: str, size: int):
        self._name = name
        self._size = size

    def get_longname(self) -> str:
        return self._name

    def get_filesize(self) -> int:
        return self._size


class _Share:
    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.dirs: list[str] = []
        self.puts = 0

    def createDirectory(self, share: str, path: str) -> None:
        self.dirs.append(path)

    def listPath(self, share: str, pattern: str):
        directory = pattern[:-2] if pattern.endswith("\\*") else pattern
        prefix = directory + "\\"
        return [
            _Item(path[len(prefix) :], len(payload))
            for path, payload in self.files.items()
            if path.startswith(prefix) and "\\" not in path[len(prefix) :]
        ]

    def putFile(self, share: str, path: str, callback) -> None:
        self.puts += 1
        chunks = []
        while True:
            block = callback(1024)
            if not block:
                break
            chunks.append(block)
        self.files[path] = b"".join(chunks)

    def close(self) -> None:
        return None


def _files() -> dict[str, bytes]:
    return {
        "EP01-U01-p1010-pass1_00001-audio.mp4": b"mp4-bytes",
        "ep01_u01_p1010_00001.safetensors": b"latent",
        "prompt_h3.txt": b"prompt",
        "prompt_source.txt": b"source",
        "prompt_audit.json": b"{}",
        "run_meta.json": b"meta",
    }


def test_selection_drops_prompt_source_and_audit():
    chosen = select_archive_files(_files())
    assert [name for name, _payload in chosen] == [
        "EP01-U01-p1010-pass1_00001-audio.mp4",
        "ep01_u01_p1010_00001.safetensors",
        "prompt_h3.txt",
        "run_meta.json",
    ]


def test_two_mp4s_are_rejected():
    files = _files()
    files["extra.mp4"] = b"second"
    try:
        select_archive_files(files)
    except RuntimeError as exc:
        assert "archive file set invalid" in str(exc)
    else:
        raise AssertionError("expected reject")


def test_selection_accepts_dialogue_qc_pair():
    files = _files()
    files["EP01-U01.srt"] = b"srt"
    files["dialogue_check.json"] = b"{}"
    names = [name for name, _payload in select_archive_files(files)]
    assert len(names) == 6
    assert "EP01-U01.srt" in names and "dialogue_check.json" in names


def test_add_qc_files_lands_pair_in_unit_folder():
    from comfy_orch.feiniu_archive import add_qc_files

    share = _Share()
    directory = add_qc_files(
        "EP01-U01.srt", b"srt", b"{}",
        batch="batch", episode="EP01", unit="U01", smb=share,
    )
    assert directory == remote_unit_dir("batch", "EP01", "U01")
    stored = {path.split("\\")[-1] for path in share.files}
    assert stored == {"EP01-U01.srt", "dialogue_check.json"}
    puts = share.puts
    add_qc_files("EP01-U01.srt", b"srt", b"{}",
                 batch="batch", episode="EP01", unit="U01", smb=share)
    assert share.puts == puts


def test_upload_lands_in_the_batch_episode_unit_folder():
    share = _Share()
    directory = archive_named_files(
        _files(),
        batch="这杯奶茶你请不起（10.10）",
        episode="EP01-奶茶-10.10",
        unit="U01",
        smb=share,
    )
    assert directory == remote_unit_dir("这杯奶茶你请不起（10.10）", "EP01-奶茶-10.10", "u01")
    assert directory.endswith("\\这杯奶茶你请不起（10.10）\\EP01\\U01")
    stored = {path.split("\\")[-1]: payload for path, payload in share.files.items()}
    assert stored["prompt_h3.txt"] == b"prompt"
    assert "prompt_source.txt" not in stored
    assert share.puts == 4


def test_matching_remote_size_is_not_uploaded_again():
    share = _Share()
    archive_named_files(_files(), batch="batch", episode="EP02", unit="U03", smb=share)
    puts = share.puts
    archive_named_files(_files(), batch="batch", episode="EP02", unit="U03", smb=share)
    assert share.puts == puts
