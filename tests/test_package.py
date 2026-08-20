def test_package_imports():
    import lithoshape3d

    assert lithoshape3d.__version__ == "0.2.0"


def test_cli_version(capsys):
    from lithoshape3d.cli import main

    exit_code = main(["--version"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "lithoshape3d" in captured.out
