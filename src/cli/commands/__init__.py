"""
Zenic CLI — Comandos
Cada subcomando en su propio archivo, importados y registrados aquí.
"""

from src.cli.commands.helpers import (
    _bump_version,
    _check_abstract_methods,
    _check_auth_compatibility,
    _check_base_connector_inheritance,
    _check_python_syntax,
    _check_required_files,
    _check_schema,
    _format_validation_report,
    _import_connector_module,
    _import_schema_module,
    _load_connector,
    _package_connector,
    _parse_input,
    _read_version,
    _run_validation,
    _update_version_in_files,
    _upload_connector,
)
from src.cli.commands.info_cmd import cmd_info
from src.cli.commands.init_cmd import cmd_init
from src.cli.commands.list_cmd import cmd_list
from src.cli.commands.parser import build_parser
from src.cli.commands.publish_cmd import cmd_publish
from src.cli.commands.test_cmd import cmd_test
from src.cli.commands.validate_cmd import cmd_validate
from src.cli.commands.version_cmd import cmd_version

COMMAND_MAP: dict[str, object] = {
    "init": cmd_init,
    "test": cmd_test,
    "validate": cmd_validate,
    "publish": cmd_publish,
    "version": cmd_version,
    "list": cmd_list,
    "info": cmd_info,
}

__all__ = [
    "COMMAND_MAP",
    "_bump_version",
    "_check_abstract_methods",
    "_check_auth_compatibility",
    "_check_base_connector_inheritance",
    "_check_python_syntax",
    "_check_required_files",
    "_check_schema",
    "_format_validation_report",
    "_import_connector_module",
    "_import_schema_module",
    "_load_connector",
    "_package_connector",
    "_parse_input",
    "_read_version",
    "_run_validation",
    "_update_version_in_files",
    "_upload_connector",
    "build_parser",
    "cmd_info",
    "cmd_init",
    "cmd_list",
    "cmd_publish",
    "cmd_test",
    "cmd_validate",
    "cmd_version",
]
