from app.bot.main import build_dispatcher


def test_build_dispatcher_registers_all_routers():
    dp = build_dispatcher()

    included_names = {router.name for router in dp.sub_routers}

    assert included_names == {"start", "admin", "group_chat", "engineer", "documents", "todo", "chat"}
