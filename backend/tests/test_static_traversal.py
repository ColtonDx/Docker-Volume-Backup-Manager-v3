from app.main import safe_static_file


def test_serves_real_file_inside_root(tmp_path):
    (tmp_path / "robots.txt").write_text("hi")
    result = safe_static_file(tmp_path.resolve(), "robots.txt")
    assert result is not None and result.name == "robots.txt"


def test_empty_path_returns_none(tmp_path):
    assert safe_static_file(tmp_path.resolve(), "") is None


def test_missing_file_returns_none(tmp_path):
    assert safe_static_file(tmp_path.resolve(), "nope.txt") is None


def test_parent_traversal_blocked(tmp_path):
    root = tmp_path / "static"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("SECRET")
    # ../secret.txt escapes the static root and must be rejected
    assert safe_static_file(root.resolve(), "../secret.txt") is None


def test_deep_traversal_blocked(tmp_path):
    root = tmp_path / "static"
    root.mkdir()
    assert safe_static_file(root.resolve(), "../../etc/passwd") is None
