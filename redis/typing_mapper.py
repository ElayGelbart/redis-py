import ast
import sys

original_sys_path = sys.path.copy()
sys.path = original_sys_path[1:]
from typing import get_type_hints

sys.path = original_sys_path
from typing import get_type_hints


def get_return_types_from_function(func):
    hints = get_type_hints(func)
    return_type = hints.get("return")
    return str(return_type) if return_type else None


def get_return_types_from_file(filename):
    with open(filename, "r") as file:
        tree = ast.parse(file.read(), filename=filename)

    functions_return_types = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Using compile and exec to generate a function object
            func_code = ast.unparse(node)
            local_scope = {}
            print(f"Compiling function {node.name}, code: {func_code}")
            exec(func_code, globals(), local_scope)
            func_obj = local_scope[node.name]

            # Get return types including generics
            return_type_annotation = get_return_types_from_function(func_obj)
            functions_return_types[node.name] = return_type_annotation

    return functions_return_types


if __name__ == "__main__":
    filename = "redis/commands/core.py"
    return_types = get_return_types_from_file(filename)
    print(return_types)
