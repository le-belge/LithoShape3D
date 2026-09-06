def test_package_imports():
    import lithoshape3d

    assert lithoshape3d.__version__ == "0.6.0"


def test_package_metadata_version_matches_module_version():
    """Source de verite unique : pyproject.toml lit sa version depuis
    `__init__.py` (tool.hatch.version.path) -- ce test garde les deux
    synchronises (regression du hotfix 0.3.1 : le titre de fenetre affichait
    encore 0.2.0 alors que pyproject.toml avait ete bascule a 0.3.0 a la
    main, sans mettre a jour `__init__.py`)."""
    from importlib.metadata import version

    import lithoshape3d

    assert version("lithoshape3d") == lithoshape3d.__version__


def test_cli_version(capsys):
    from lithoshape3d.cli import main

    exit_code = main(["--version"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "lithoshape3d" in captured.out
