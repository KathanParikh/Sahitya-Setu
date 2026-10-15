"""Retry policy in qa.llm_client, driven by the real SDK exception classes."""
import unittest
from unittest import mock

import tests.helpers  # noqa: F401  (sets fake API keys)
import httpx
import groq
from google.genai import errors as gerr

from qa import llm_client
from qa.llm_client import BaseLLM, FallbackLLM, GroqLLM, LLMError


def gemini_err(code, status, quota_id=None, retry="8s"):
    details = []
    if quota_id:
        details.append({"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [{"quotaId": quota_id}]})
    if retry:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry})
    return gerr.APIError(code, {"error": {"code": code, "status": status,
                                          "message": "x", "details": details}})


def groq_429(retry_after):
    req = httpx.Request("POST", "https://api.groq.com/x")
    resp = httpx.Response(429, headers={"retry-after": retry_after}, request=req)
    return groq.RateLimitError("rate limited", response=resp, body=None)


class Scripted(BaseLLM):
    name = "scripted"

    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    def _complete(self, prompt, system, temperature):
        self.calls += 1
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return o


class RetryPolicy(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(llm_client.time, "sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def waits(self):
        return [c.args[0] for c in self.sleep.call_args_list]

    def test_gemini_429_honours_retry_info(self):
        llm = Scripted([gemini_err(429, "RESOURCE_EXHAUSTED",
                                   "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"), "ok"])
        self.assertEqual(llm.generate("p", max_retries=3), "ok")
        self.assertTrue(8 <= self.waits()[0] <= 9, self.waits())

    def test_retry_hint_parsed_from_message(self):
        exc = gerr.APIError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                            "message": "Please retry in 12.5s."}})
        self.assertEqual(llm_client.provider_retry_after(exc), 12.5)

    def test_503_backs_off_exponentially_then_gives_up(self):
        llm = Scripted([gemini_err(503, "UNAVAILABLE", retry=None)] * 3)
        with self.assertRaises(LLMError):
            llm.generate("p", max_retries=3)
        w = self.waits()
        self.assertEqual(llm.calls, 3)
        self.assertTrue(2 <= w[0] <= 3 and 4 <= w[1] <= 5, w)

    def test_429_without_hint_waits_minimum(self):
        llm = Scripted([gemini_err(429, "RESOURCE_EXHAUSTED", retry=None), "ok"])
        llm.generate("p", max_retries=3)
        self.assertTrue(10 <= self.waits()[0] <= 11, self.waits())

    def test_groq_retry_after_header(self):
        llm = Scripted([groq_429("7"), "ok"])
        self.assertEqual(llm.generate("p", max_retries=3), "ok")
        self.assertTrue(7 <= self.waits()[0] <= 8, self.waits())

    def test_permanent_errors_fail_fast(self):
        for code, status in [(400, "INVALID_ARGUMENT"), (401, "UNAUTHENTICATED"),
                             (403, "PERMISSION_DENIED"), (404, "NOT_FOUND")]:
            self.sleep.reset_mock()
            llm = Scripted([gemini_err(code, status, retry=None), "never"])
            with self.assertRaises(LLMError):
                llm.generate("p", max_retries=3)
            self.assertEqual(llm.calls, 1, code)
            self.sleep.assert_not_called()

    def test_daily_quota_not_retried(self):
        llm = Scripted([gemini_err(429, "RESOURCE_EXHAUSTED",
                                   "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "30s"), "never"])
        with self.assertRaises(LLMError):
            llm.generate("p", max_retries=3)
        self.assertEqual(llm.calls, 1)

    def test_hint_longer_than_cap_gives_up(self):
        llm = Scripted([gemini_err(429, "RESOURCE_EXHAUSTED", retry="120s"), "never"])
        with self.assertRaises(LLMError):
            llm.generate("p", max_retries=3)
        self.assertEqual(llm.calls, 1)
        self.sleep.assert_not_called()

    def test_connection_error_and_empty_response_retried(self):
        self.assertEqual(Scripted([httpx.ConnectError("boom"), "ok"]).generate("p", max_retries=3), "ok")
        self.assertEqual(Scripted(["  ", "ok"]).generate("p", max_retries=3), "ok")

    def test_fallback_after_primary_quota(self):
        primary = Scripted([gemini_err(429, "RESOURCE_EXHAUSTED", "PerDay-x", "5s")])
        backup = Scripted(["from backup"])
        self.assertEqual(FallbackLLM(primary, backup).generate("p"), "from backup")

    def test_groq_sdk_retries_disabled(self):
        self.assertEqual(GroqLLM()._get_client().max_retries, 0)

    def test_call_llm_uses_configured_provider(self):
        llm_client.reset_llm()
        with mock.patch.object(llm_client.config, "LLM_PROVIDER", "groq"), \
             mock.patch.object(llm_client.config, "LLM_AUTO_FALLBACK", False), \
             mock.patch.object(GroqLLM, "_complete", return_value="hi"):
            self.assertEqual(llm_client.call_llm("p"), "hi")
            self.assertIsInstance(llm_client.get_llm(), GroqLLM)
        llm_client.reset_llm()


if __name__ == "__main__":
    unittest.main()
