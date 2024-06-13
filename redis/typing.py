# from __future__ import annotations

import ast
import sys
from datetime import datetime, timedelta

import bs4

original_sys_path = sys.path.copy()
sys.path = original_sys_path[1:]
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import requests

sys.path = original_sys_path
if TYPE_CHECKING:
    from redis._parsers import Encoder
    from redis.asyncio.connection import ConnectionPool as AsyncConnectionPool
    from redis.connection import ConnectionPool


Number = Union[int, float]
EncodedT = Union[bytes, memoryview]
DecodedT = Union[str, int, float]
EncodableT = Union[EncodedT, DecodedT]
AbsExpiryT = Union[int, datetime]
ExpiryT = Union[int, timedelta]
ZScoreBoundT = Union[float, str]  # str allows for the [ or ( prefix
BitfieldOffsetT = Union[int, str]  # str allows for #x syntax
_StringLikeT = Union[bytes, str, memoryview]
KeyT = _StringLikeT  # Main redis key space
PatternT = _StringLikeT  # Patterns matched against keys, fields etc
FieldT = EncodableT  # Fields within hash tables, streams and geo commands
KeysT = Union[KeyT, Iterable[KeyT]]
OldResponseT = Union[Awaitable[Any], Any]  # Deprecated
AnyResponseT = TypeVar("AnyResponseT", bound=Any)
ResponseT = Union[AnyResponseT, Awaitable[AnyResponseT]]
OKT = Literal["OK"]
ArrayResponseT = list
IntegerResponseT = int
NullResponseT = type(None)
BulkStringResponseT = str
ChannelT = _StringLikeT
GroupT = _StringLikeT  # Consumer group
ConsumerT = _StringLikeT  # Consumer name
StreamIdT = Union[int, _StringLikeT]
ScriptTextT = _StringLikeT
TimeoutSecT = Union[int, float, _StringLikeT]
# Mapping is not covariant in the key type, which prevents
# Mapping[_StringLikeT, X] from accepting arguments of type Dict[str, X]. Using
# a TypeVar instead of a Union allows mappings with any of the permitted types
# to be passed. Care is needed if there is more than one such mapping in a
# type signature because they will all be required to be the same key type.
AnyKeyT = TypeVar("AnyKeyT", bytes, str, memoryview)
AnyFieldT = TypeVar("AnyFieldT", bytes, str, memoryview)
AnyChannelT = TypeVar("AnyChannelT", bytes, str, memoryview)

ExceptionMappingT = Mapping[str, Union[Type[Exception], Mapping[str, Type[Exception]]]]


class CommandsProtocol(Protocol):
    connection_pool: Union["AsyncConnectionPool", "ConnectionPool"]

    def execute_command(self, *args, **options) -> ResponseT[Any]: ...


class ClusterCommandsProtocol(CommandsProtocol, Protocol):
    encoder: "Encoder"

    def execute_command(self, *args, **options) -> Union[Any, Awaitable]: ...


ignore_function_names = [
    "__init__",
    "__new__",
    "__repr__",
    "__str__",
    "__eq__",
    "__call__",
    "get_encoder",
    "__contains__",
    "_tf",
    "tf",
]

functions_changed = []
functions_not_changed = []
no_exec_function_list = []
no_return_function_list = []
no_found_in_official_docs = []
not_found_all_types = []


def redis_string_to_type(redis_type_string: str):
    if redis_type_string.startswith("Array reply"):
        return "ArrayResponseT"
    elif redis_type_string.startswith(
        "Simple string reply: OK"
    ) or redis_type_string.startswith("Simple string reply:OK"):
        return "OKT"
    elif redis_type_string.startswith("Integer reply"):
        return "IntegerResponseT"
    elif redis_type_string.startswith("Nil reply") or redis_type_string.startswith(
        "Null reply"
    ):
        return "NullResponseT"
    elif redis_type_string.startswith("Bulk string reply"):
        return "BulkStringResponseT"
    elif redis_type_string.startswith("Simple string reply"):
        return "str"
    print(f"Unknown type Do Not IGNORE {redis_type_string}")
    not_found_all_types.append(redis_type_string)
    return "Ignore me"


def change_python_function_TODO_type(function_node: ast.FunctionDef):
    print(f"Changing {function_node.name} return type to None")
    function_node.returns = ast.Name(id="TODO", ctx=ast.Load())
    return None


def change_python_function_no_return_type(function_node: ast.FunctionDef):
    print(f"Changing {function_node.name} return type to None")
    function_node.returns = ast.Name(id="None", ctx=ast.Load())
    return None


def change_python_function_return_type(
    function_node: ast.FunctionDef, return_types: list[str]
):
    if len(return_types) > 1:
        print(
            f"Changing {function_node.name} return type to ResponseT[Union{return_types}]"
        )
        # check if type is subscript
        return_slice = ast.Subscript(
            value=ast.Name(id="Union", ctx=ast.Load()),
            slice=ast.Tuple(
                elts=[
                    ast.Name(id=str(sing_return_type), ctx=ast.Load())
                    for sing_return_type in return_types
                ],
            ),
        )
    elif len(return_types) == 1:
        print(
            f"Changing {function_node.name} return type to ResponseT[{return_types[0]}]"
        )
        return_slice = ast.Name(id=str(return_types[0]), ctx=ast.Load())
    function_node.returns = ast.Subscript(
        value=ast.Name(id="ResponseT", ctx=ast.Load()),
        slice=return_slice,
    )
    return None


def get_official_type_hints(function_name: str, execute_command: str):
    redis_base_commands_url = "https://redis.io/docs/latest/commands"
    url_command_name = execute_command.lower().replace("_", "-").replace(" ", "-")
    print(f"Checking Function: {function_name} with URL Param: {url_command_name}")
    response = requests.get(f"{redis_base_commands_url}/{url_command_name}/")
    if len(response.history) > 1:
        no_found_in_official_docs.append(function_name)
        raise Exception(f"Cannot find {function_name} in official redis docs")
    soup = bs4.BeautifulSoup(response.text, "html.parser")
    returns_type_list = []
    for reply_header_html_id in [
        "resp2resp3-reply",
        "resp2resp3-replies",
        "resp2-reply",
    ]:
        reply_element_header = soup.find(None, {"id": reply_header_html_id})
        if not reply_element_header:
            if reply_header_html_id == "resp2-reply":
                raise Exception(
                    f"Couldn't find response HEADER for Function: {function_name} in DOCS"
                )
            continue
        below_element = reply_element_header.find_next_sibling()
        if not below_element:
            raise Exception(
                f"Couldn't find below element for {function_name} with id {reply_header_html_id}"
            )
        if (
            below_element.text.find("One of the following:") > -1
            or below_element.text.find("Any of the following:") > -1
            or below_element.name == "ul"
        ):
            next_ul_element = (
                below_element
                if below_element.name == "ul"
                else below_element.find_next("ul")
            )
            if not next_ul_element or isinstance(next_ul_element, bs4.NavigableString):
                raise Exception(
                    f"Couldn't find next UL element for Function: {function_name}"
                )
            for li_element in next_ul_element.find_all("li"):
                type_hint = redis_string_to_type(li_element.text)
                returns_type_list.append(type_hint)
            return returns_type_list

        elif below_element.name == "p":
            has_a_inside = below_element.find("a")
            if has_a_inside:
                type_hint = redis_string_to_type(has_a_inside.text)
                return [type_hint]

        elif below_element.name == "a":
            text = below_element.text
            text_in_next_code = below_element.find_next("code")
            if text_in_next_code:
                text += f": {text_in_next_code.text}"
            type_hint = redis_string_to_type(text)
            return [type_hint]

        next_ul_before_h_element = below_element.find_next("ul")
        if next_ul_before_h_element and not isinstance(
            next_ul_before_h_element, bs4.NavigableString
        ):
            for li_element in next_ul_before_h_element.find_all("li"):
                type_hint = redis_string_to_type(li_element.text)
                returns_type_list.append(type_hint)
            return returns_type_list

        if below_element.text.find("Non-standard return value") > -1:
            return ["Any"]

        print(f"couldn't find type hint in response for Function: {function_name}")
        print(f"below element is {below_element}")
        is_this_ok = input("y/n: ")
        if is_this_ok == "y":
            continue
        return None
    print(f"found {function_name} and change response typing")


def get_return_types_from_file_without_exec(filename):
    with open(filename, "r") as file:
        tree = ast.parse(file.read(), filename=filename)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            is_ignored = False
            for ignore_function_name in ignore_function_names:
                if node.name.startswith(ignore_function_name):
                    is_ignored = True
            if is_ignored:
                continue
            all_return_statements = [
                statement
                for statement in node.body
                if isinstance(statement, ast.Return)
            ]
            try:
                if not all_return_statements:
                    if isinstance(node.body[0], ast.Raise) or isinstance(
                        node.body[1], ast.Raise
                    ):
                        change_python_function_no_return_type(node)
                        no_return_function_list.append(node.name)
                        continue
                    raise Exception(f"Function {node.name} has no return")
                has_no_exec_return = False
                for return_statement in all_return_statements:
                    if return_statement.value.func.attr != "execute_command":
                        no_exec_function_list.append(node.name)
                        has_no_exec_return = True
                if has_no_exec_return:
                    continue

                if len(all_return_statements) > 1:
                    raise Exception(
                        f"Function {node.name} has multiple return execute_command"
                    )
                execute_command = all_return_statements[0].value.args[0].value
                if not isinstance(execute_command, str):
                    if execute_command.id == "args":
                        execute_command = node.name
                    else:
                        no_exec_function_list.append(node.name)
                        raise Exception(
                            f"Function {node.name} has no execute_command return"
                        )
                print(
                    f"Function {node.name} is valid and only returns execute_command {execute_command}"
                )
                function_official_type = get_official_type_hints(
                    node.name, execute_command
                )
                if function_official_type:
                    function_official_type = [
                        type_hint
                        for type_hint in function_official_type
                        if type_hint != "Ignore me"
                    ]
                    if len(function_official_type) == 0:
                        raise Exception(
                            f"Function {node.name} has only Ignore me types"
                        )
                    function_official_type = list(set(function_official_type))
                    change_python_function_return_type(node, function_official_type)
                    functions_changed.append(node.name)
            except Exception as e:
                print("ERROR")
                print(e)
                print("ERROR")

                functions_not_changed.append(f"Function error - {node.name} : {e}")
                change_python_function_TODO_type(node)
            print("\n")
    with open(filename, "w") as file:
        file.write(ast.unparse(tree))
    print(f"Changed {len(functions_changed)} functions")
    print(f"Not Changed {len(functions_not_changed)} functions")
    for not_changed in functions_not_changed:
        with open("not_changed.txt", "a") as file:
            file.write(f"{not_changed}\n")
    return None


if __name__ == "__main__":
    filename = "redis/commands/core.py"
    return_types = get_return_types_from_file_without_exec(filename)
    print(return_types)
