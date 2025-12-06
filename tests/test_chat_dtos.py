import argparse

from termi_cli.application.chat_service import ChatLoopOptions, HttpChatOptions


def test_chat_loop_options_from_args_uses_config_and_args():
    config = {"language": "en", "default_model": "models/gemini-pro"}
    args = argparse.Namespace(model=None, topic="my-topic", load="history.json")

    opts = ChatLoopOptions.from_args(config, args)

    assert opts.language == "en"
    assert opts.model_name == "models/gemini-pro"
    assert opts.topic == "my-topic"
    assert opts.load_path == "history.json"


def test_chat_loop_options_model_overrides_default():
    config = {"language": "vi", "default_model": "models/gemini-pro"}
    args = argparse.Namespace(model="models/gemini-flash", topic=None, load=None)

    opts = ChatLoopOptions.from_args(config, args)

    assert opts.model_name == "models/gemini-flash"


def test_http_chat_options_from_args():
    config = {"language": "vi", "default_model": "models/gemini-pro"}
    args = argparse.Namespace(model=None, mini_agent_off=True)

    opts = HttpChatOptions.from_args(config, args)

    assert opts.language == "vi"
    assert opts.model_name == "models/gemini-pro"
    assert opts.mini_agent_off is True
