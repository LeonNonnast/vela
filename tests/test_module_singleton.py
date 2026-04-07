"""Module Singleton Tests — all modules using VelaModuleBase."""

from tests.conftest import make_mock_mcp, reset_all_singletons, reset_singleton

from src.mcp.modules.base import VelaModuleBase


class TestResetAllSingletons:
    def test_reset_all_is_noop_after_cleanup(self):
        """After reset, all singletons should be None."""
        reset_all_singletons()

    def test_admin_module_singleton(self):
        """AdminModule should follow singleton pattern via VelaModuleBase."""
        from src.mcp.modules.vela_module import AdminModule
        reset_singleton(AdminModule)

        mock_mcp = make_mock_mcp()
        mock_mcp._prompts = {}
        def capture_prompt(name: str, description: str = ""):
            def decorator(func):
                mock_mcp._prompts[name] = {"handler": func, "description": description}
                return func
            return decorator
        mock_mcp.prompt = capture_prompt

        instance1 = AdminModule.construct(mcp=mock_mcp)
        instance2 = AdminModule.construct(mcp=mock_mcp)
        assert instance1 is instance2

        reset_singleton(AdminModule)
        assert AdminModule._instance is None

    def test_base_class_reset_all(self):
        """VelaModuleBase.reset_all() should clear all instances."""
        from src.mcp.modules.vela_module import AdminModule
        mock_mcp = make_mock_mcp()
        mock_mcp._prompts = {}
        def capture_prompt(name: str, description: str = ""):
            def decorator(func):
                mock_mcp._prompts[name] = {"handler": func, "description": description}
                return func
            return decorator
        mock_mcp.prompt = capture_prompt

        AdminModule.construct(mcp=mock_mcp)
        assert AdminModule.instance() is not None

        VelaModuleBase.reset_all()
        assert AdminModule.instance() is None
