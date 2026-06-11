"""
Tests para Code Runner (Sprint 6).
Valida ejecución segura de Python: sandbox, timeout, seguridad.
"""


class TestCodeSandbox:
    """Tests para el sandbox de ejecución segura."""

    def test_execute_simple_python(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python("result = 2 + 2")
        assert result.success is True
        assert result.output == {"result": 4}

    def test_execute_with_input_vars(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python(
            "result = x + y",
            input_vars={"x": 10, "y": 20},
        )
        assert result.success is True
        assert result.output == {"result": 30}

    def test_execute_list_comprehension(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        code = "result = [x * 2 for x in range(5)]"
        result = sandbox.execute_python(code)
        assert result.success is True
        assert result.output == {"result": [0, 2, 4, 6, 8]}

    def test_execute_dict_manipulation(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        code = """
items = [{"name": "A", "price": 10}, {"name": "B", "price": 20}]
result = {"total": sum(i["price"] for i in items), "count": len(items)}
"""
        result = sandbox.execute_python(code, input_vars={"items": None})
        assert result.success is True
        assert result.output["result"]["total"] == 30
        assert result.output["result"]["count"] == 2

    def test_execute_string_operations(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        code = 'result = "hello world".upper().replace(" ", "_")'
        result = sandbox.execute_python(code)
        assert result.success is True
        assert result.output == {"result": "HELLO_WORLD"}

    def test_execute_math_operations(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        code = "import math\nresult = math.sqrt(144)"
        result = sandbox.execute_python(code)
        assert result.success is True
        assert result.output == {"result": 12.0}

    def test_execute_captures_stdout(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        code = 'print("hello from sandbox")\nresult = 42'
        result = sandbox.execute_python(code)
        assert result.success is True
        assert "hello from sandbox" in result.stdout
        assert result.output == {"result": 42}

    def test_syntax_error(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python("def foo(")
        assert result.success is False
        assert "sintaxis" in result.error.lower()

    def test_empty_code(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python("")
        assert result.success is False
        assert "vacío" in result.error.lower()

    def test_execution_error(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python("result = 1 / 0")
        assert result.success is False
        assert "ZeroDivisionError" in result.error

    def test_execution_time_recorded(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python("result = 1")
        assert result.execution_time_ms >= 0


class TestCodeSandboxSecurity:
    """Tests de seguridad del sandbox."""

    def test_blocks_import_os(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python("import os\nresult = os.getcwd()")
        assert result.success is False
        assert "prohibido" in result.error.lower() or "bloqueado" in result.error.lower()

    def test_blocks_import_sys(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python("import sys\nresult = sys.version")
        assert result.success is False

    def test_blocks_import_subprocess(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python("import subprocess\nresult = subprocess.run(['ls'])")
        assert result.success is False

    def test_blocks_eval(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python("result = eval(\"__import__('os').getcwd()\")")
        assert result.success is False

    def test_blocks_exec(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python('exec("import os")')
        assert result.success is False

    def test_blocks_open(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python('result = open("/etc/passwd").read()')
        assert result.success is False

    def test_blocks_from_os_import(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python("from os import path")
        assert result.success is False

    def test_blocks_dunder_import(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python('result = __import__("os")')
        assert result.success is False

    def test_blocks_socket(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python("import socket\nresult = socket.socket()")
        assert result.success is False

    def test_blocks_requests(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        result = sandbox.execute_python("import requests\nresult = requests.get('http://evil.com')")
        assert result.success is False

    def test_validate_source_safe(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        error = sandbox._validate_source("result = 1 + 2")
        assert error is None

    def test_validate_source_dangerous(self):
        from src.tools.code_runner.sandbox import CodeSandbox

        sandbox = CodeSandbox()
        error = sandbox._validate_source("import os")
        assert error is not None
        assert "os" in error


class TestCodeRunnerTool:
    """Tests para CodeRunnerTool (service layer)."""

    def test_run_python_success(self):
        from src.tools.code_runner.service import CodeRunnerTool

        tool = CodeRunnerTool()
        result = tool.run_python(code="result = 10 * 5")
        assert result["success"] is True
        assert result["output"]["result"] == 50

    def test_run_python_empty_code(self):
        from src.tools.code_runner.service import CodeRunnerTool

        tool = CodeRunnerTool()
        result = tool.run_python(code="")
        assert result["success"] is False
        assert "vacío" in result["error"].lower()

    def test_run_python_syntax_error(self):
        from src.tools.code_runner.service import CodeRunnerTool

        tool = CodeRunnerTool()
        result = tool.run_python(code="def foo(")
        assert result["success"] is False

    def test_run_python_blocked_import(self):
        from src.tools.code_runner.service import CodeRunnerTool

        tool = CodeRunnerTool()
        result = tool.run_python(code="import os")
        assert result["success"] is False

    def test_run_python_execution_time(self):
        from src.tools.code_runner.service import CodeRunnerTool

        tool = CodeRunnerTool()
        result = tool.run_python(code="result = sum(range(100))")
        assert result["execution_time_ms"] >= 0

    def test_validate_safe_code(self):
        from src.tools.code_runner.service import CodeRunnerTool

        tool = CodeRunnerTool()
        result = tool.validate(code="result = 1 + 2")
        assert result["valid"] is True
        assert result["errors"] == []

    def test_validate_dangerous_code(self):
        from src.tools.code_runner.service import CodeRunnerTool

        tool = CodeRunnerTool()
        result = tool.validate(code="import os")
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_validate_empty_code(self):
        from src.tools.code_runner.service import CodeRunnerTool

        tool = CodeRunnerTool()
        result = tool.validate(code="")
        assert result["valid"] is False

    def test_validate_syntax_error(self):
        from src.tools.code_runner.service import CodeRunnerTool

        tool = CodeRunnerTool()
        result = tool.validate(code="def foo(")
        assert result["valid"] is False

    def test_tool_definition(self):
        from src.tools.code_runner.service import CodeRunnerTool

        defn = CodeRunnerTool.get_tool_definition()
        assert defn["tool"] == "code_runner"
        assert "run_python" in defn["actions"]
        assert "validate" in defn["actions"]

    def test_tool_definition_params(self):
        from src.tools.code_runner.service import CodeRunnerTool

        defn = CodeRunnerTool.get_tool_definition()
        run_params = defn["actions"]["run_python"]["params"]
        assert len(run_params) == 4  # code, input_vars, output_var, timeout
        param_names = [p["name"] for p in run_params]
        assert "code" in param_names
        assert "output_var" in param_names
