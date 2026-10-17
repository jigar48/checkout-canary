import json

import pytest

from checkout_canary.alerts import (
    AlertError,
    FailureAlert,
    TelegramNotifier,
    notifiers_from_env,
    redact,
    run_url_from_env,
    send_alerts,
)
from checkout_canary.cli import main
from checkout_canary.results import Evidence, StepResult, build_result
from conftest import EXAMPLE_JOURNEY, FakeTelegram

TOKEN = "123456:FAKE-token-for-tests"
CHAT = "-1001234567890"


def failed_result():
    steps = [
        StepResult(index=1, action="goto", target="/", status="passed", duration_ms=5),
        StepResult(
            index=2,
            action="expect_visible",
            target="#checkout-button",
            status="failed",
            duration_ms=3000,
            error="'#checkout-button' was not visible after 3s",
        ),
        StepResult(index=3, action="click", target="#checkout-button", status="skipped"),
    ]
    return build_result(
        journey="Demo shop checkout",
        base_url="http://x.test",
        steps=steps,
        evidence=Evidence(),
        started_at="2026-10-17T10:00:00+00:00",
        duration_ms=3100,
    )


def test_alert_text_is_plain_english():
    text = FailureAlert.from_result(failed_result(), "https://ci.test/run/1").text()
    assert text.splitlines() == [
        "Checkout check FAILED: Demo shop checkout",
        "It stopped at step 2 of 3, while waiting for #checkout-button to appear.",
        "Reason: '#checkout-button' was not visible after 3s",
        "Time (UTC): 2026-10-17T10:00:00+00:00",
        "Run details: https://ci.test/run/1",
    ]


def test_alert_text_without_run_url_and_long_reason_is_trimmed():
    result = failed_result()
    result.steps[1].error = "x" * 2000
    text = FailureAlert.from_result(result).text()
    assert "Run details" not in text
    assert len(text) < 1000


def test_notifiers_from_env():
    assert notifiers_from_env({})[0] == []
    assert "Alerts are off" in notifiers_from_env({})[1][0]
    only_token = notifiers_from_env({"CHECKOUT_CANARY_TELEGRAM_TOKEN": TOKEN})
    assert only_token[0] == []
    assert "CHECKOUT_CANARY_TELEGRAM_CHAT_ID is not set" in only_token[1][0]
    blank = notifiers_from_env(
        {"CHECKOUT_CANARY_TELEGRAM_TOKEN": "", "CHECKOUT_CANARY_TELEGRAM_CHAT_ID": " "}
    )
    assert blank[0] == []
    both = notifiers_from_env(
        {"CHECKOUT_CANARY_TELEGRAM_TOKEN": TOKEN, "CHECKOUT_CANARY_TELEGRAM_CHAT_ID": CHAT}
    )
    assert [n.name for n in both[0]] == ["telegram"]


def test_run_url_from_env():
    assert run_url_from_env({}) is None
    github = {
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "o/r",
        "GITHUB_RUN_ID": "42",
    }
    assert run_url_from_env(github) == "https://github.com/o/r/actions/runs/42"
    assert run_url_from_env({**github, "CHECKOUT_CANARY_RUN_URL": "https://x"}) == "https://x"


def test_redact():
    assert redact(f"bad {TOKEN} here", [TOKEN, ""]) == "bad [redacted] here"


def test_telegram_sends_send_message(fake_telegram: FakeTelegram):
    alert = FailureAlert.from_result(failed_result())
    TelegramNotifier(TOKEN, CHAT, fake_telegram.base_url).send(alert)

    (request,) = fake_telegram.requests
    assert request["path"] == f"/bot{TOKEN}/sendMessage"
    assert request["body"]["chat_id"] == CHAT
    assert request["body"]["text"] == alert.text()
    assert request["body"]["link_preview_options"] == {"is_disabled": True}


def test_telegram_http_error_does_not_leak_token(fake_telegram: FakeTelegram):
    fake_telegram.status = 401
    alert = FailureAlert.from_result(failed_result())
    with pytest.raises(AlertError) as info:
        TelegramNotifier(TOKEN, CHAT, fake_telegram.base_url).send(alert)
    assert "401" in str(info.value)
    assert "Unauthorized" in str(info.value)
    assert TOKEN not in str(info.value)


def test_telegram_unreachable_does_not_leak_token():
    notifier = TelegramNotifier(TOKEN, CHAT, "http://127.0.0.1:9", timeout=1)
    with pytest.raises(AlertError) as info:
        notifier.send(FailureAlert.from_result(failed_result()))
    assert TOKEN not in str(info.value)
    assert CHAT not in str(info.value)


def test_send_alerts_never_raises():
    notifier = TelegramNotifier(TOKEN, CHAT, "http://127.0.0.1:9", timeout=1)
    lines = send_alerts([notifier], FailureAlert.from_result(failed_result()))
    assert lines[0].startswith("Alert via telegram FAILED to send:")
    assert TOKEN not in lines[0]


def env_for(fake: FakeTelegram) -> dict[str, str]:
    return {
        "CHECKOUT_CANARY_TELEGRAM_TOKEN": TOKEN,
        "CHECKOUT_CANARY_TELEGRAM_CHAT_ID": CHAT,
        "CHECKOUT_CANARY_TELEGRAM_API_BASE": fake.base_url,
        "CHECKOUT_CANARY_RUN_URL": "https://ci.test/run/7",
    }


def run_cli(shop_url, out, env):
    argv = ["run", str(EXAMPLE_JOURNEY), "--base-url", shop_url, "--output-dir", str(out)]
    return main(argv, env=env)


def test_cli_alerts_on_failure(broken_shop_url, fake_telegram, tmp_path, capsys):
    code = run_cli(broken_shop_url, tmp_path, env_for(fake_telegram))

    assert code == 1
    (request,) = fake_telegram.requests
    text = request["body"]["text"]
    assert "Checkout check FAILED: Demo shop checkout" in text
    assert "step 8 of 12" in text
    assert "https://ci.test/run/7" in text
    output = capsys.readouterr().out
    assert "Alert sent via telegram." in output
    assert TOKEN not in output
    assert TOKEN not in (tmp_path / "result.json").read_text(encoding="utf-8")


def test_cli_no_alert_when_journey_passes(working_shop_url, fake_telegram, tmp_path, capsys):
    code = run_cli(working_shop_url, tmp_path, env_for(fake_telegram))

    assert code == 0
    assert fake_telegram.requests == []
    assert "Alert" not in capsys.readouterr().out


def test_cli_exit_code_unchanged_when_alert_fails(broken_shop_url, fake_telegram, tmp_path, capsys):
    fake_telegram.status = 401

    code = run_cli(broken_shop_url, tmp_path, env_for(fake_telegram))

    assert code == 1
    output = capsys.readouterr().out
    assert "FAILED to send" in output
    assert TOKEN not in output


def test_cli_says_alerts_are_off_without_env(broken_shop_url, tmp_path, capsys):
    assert run_cli(broken_shop_url, tmp_path, {}) == 1
    assert "Alerts are off" in capsys.readouterr().out
    assert json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))["passed"] is False
