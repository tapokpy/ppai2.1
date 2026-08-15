from app.core.tool_registry import ToolParameter, ToolRegistry, ToolResult, ToolSpec, try_parse_json


async def _noop(**kwargs) -> ToolResult:
    return ToolResult(text="ok")


def _spec(name: str, admin_only: bool = False) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=f"Делает {name}",
        parameters=[ToolParameter(name="x", type="integer", description="число")],
        handler=_noop,
        admin_only=admin_only,
    )


def test_register_and_get():
    registry = ToolRegistry()
    spec = _spec("calculate_power")

    registry.register(spec)

    assert registry.get("calculate_power") is spec
    assert registry.get("unknown") is None


def test_list_for_hides_admin_only_tools_from_non_admins():
    registry = ToolRegistry()
    registry.register(_spec("public_tool"))
    registry.register(_spec("admin_tool", admin_only=True))

    assert [t.name for t in registry.list_for(is_admin=False)] == ["public_tool"]
    assert {t.name for t in registry.list_for(is_admin=True)} == {"public_tool", "admin_tool"}


def test_to_ollama_schema_shape():
    registry = ToolRegistry()
    registry.register(_spec("calculate_power"))

    schema = registry.to_ollama_schema(is_admin=False)

    assert schema == [
        {
            "type": "function",
            "function": {
                "name": "calculate_power",
                "description": "Делает calculate_power",
                "parameters": {
                    "type": "object",
                    "properties": {"x": {"type": "integer", "description": "число"}},
                    "required": ["x"],
                },
            },
        }
    ]


def test_to_ollama_schema_excludes_admin_only_for_non_admin():
    registry = ToolRegistry()
    registry.register(_spec("admin_tool", admin_only=True))

    assert registry.to_ollama_schema(is_admin=False) == []
    assert len(registry.to_ollama_schema(is_admin=True)) == 1


def test_to_prompt_block_lists_every_visible_tool():
    registry = ToolRegistry()
    registry.register(_spec("calculate_power"))
    registry.register(_spec("admin_tool", admin_only=True))

    block = registry.to_prompt_block(is_admin=False)

    assert "calculate_power" in block
    assert "admin_tool" not in block


def test_to_prompt_block_empty_when_no_tools_visible():
    registry = ToolRegistry()

    assert registry.to_prompt_block(is_admin=False) == ""


def test_try_parse_json_valid():
    assert try_parse_json('{"tool": "x", "arguments": {}}') == {"tool": "x", "arguments": {}}


def test_try_parse_json_malformed_returns_none():
    assert try_parse_json("это не json") is None


def test_try_parse_json_none_input_returns_none():
    assert try_parse_json(None) is None
