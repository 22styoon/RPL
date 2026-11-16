"""공공 API 클라이언트의 명세·보안·재시도를 실제 네트워크 없이 검증한다."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, quote_plus, urlsplit

import pytest

from src.public_data import client as api


ENDPOINT = "https://apis.data.go.kr/123456/TestService/getItems"
TEST_KEY = "synthetic+key/=%percent"


def json_page(items=None, total=0, page=1, size=10, *, wrapped=True, code="00"):
    body = {"items": [] if items is None else items, "totalCount": total, "pageNo": page, "numOfRows": size}
    envelope = {"header": {"resultCode": code, "resultMsg": "NORMAL SERVICE"}, "body": body}
    return json.dumps({"response": envelope} if wrapped else envelope, ensure_ascii=False).encode("utf-8")


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.read_limits = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        self.read_limits.append(limit)
        return self.payload[:limit]


class ScriptedOpener:
    """urllib opener의 open/context/read 계약만 제공하는 테스트 대역."""
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.responses = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if not self.outcomes:
            raise AssertionError("예정하지 않은 추가 HTTP 요청")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        response = FakeResponse(outcome)
        self.responses.append(response)
        return response


@pytest.mark.parametrize("wrapped", [True, False])
@pytest.mark.parametrize("items,total,expected", [
    ([{"bzentyId": "A"}, {"bzentyId": "B"}], 2, [{"bzentyId": "A"}, {"bzentyId": "B"}]),
    ({"item": [{"bzentyId": "A"}, {"bzentyId": "B"}]}, 2, [{"bzentyId": "A"}, {"bzentyId": "B"}]),
    ({"item": {"bzentyId": "A"}}, 1, [{"bzentyId": "A"}]),
    ({"bzentyId": "A"}, 1, [{"bzentyId": "A"}]),
    ([], 0, []), ("", 0, []), ({"item": []}, 0, []),
])
def test_known_json_envelopes_normalize_single_multiple_empty_items(wrapped, items, total, expected):
    page = api.parse_page(json_page(items, total, wrapped=wrapped))
    assert page.items == expected
    assert page.total_count == total
    assert page.page_no == 1
    assert page.page_size == 10
    assert page.meta["format"] == "json"
    assert page.meta["envelope"] == ("response" if wrapped else "root")


@pytest.mark.parametrize("items,total,expected", [
    ("<items><item><bzentyId>A</bzentyId></item></items>", 1, [{"bzentyId": "A"}]),
    ("<items><item><bzentyId>A</bzentyId></item><item><bzentyId>B</bzentyId></item></items>", 2, [{"bzentyId": "A"}, {"bzentyId": "B"}]),
    ("<items/>", 0, []), ("", 0, []),
])
def test_xml_response_normalizes_single_multiple_empty_items(items, total, expected):
    raw = (
        '<?xml version="1.0" encoding="UTF-8"?><response>'
        '<header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>'
        f'<body>{items}<totalCount>{total}</totalCount><pageNo>1</pageNo><numOfRows>10</numOfRows></body>'
        '</response>'
    ).encode("utf-8")
    page = api.parse_page(raw)
    assert page.items == expected
    assert page.meta["format"] == "xml"


def test_xml_namespace_does_not_change_known_envelope():
    raw = b'<response xmlns="urn:test"><header><resultCode>00</resultCode></header><body><items/><totalCount>0</totalCount></body></response>'
    assert api.parse_page(raw).items == []


@pytest.mark.parametrize("raw", [
    b'<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg><returnAuthMsg>INVALID_KEY</returnAuthMsg></cmmMsgHeader></OpenAPI_ServiceResponse>',
    b'{"OpenAPI_ServiceResponse":{"cmmMsgHeader":{"returnAuthMsg":"INVALID_KEY"}}}',
])
def test_gateway_authentication_failure_is_an_error_not_empty_data(raw):
    with pytest.raises(api.PublicDataError, match="게이트웨이"):
        api.parse_page(raw)


@pytest.mark.parametrize("code", ["01", "06", "07", "08", "30", "", "UNKNOWN"])
def test_non_success_result_codes_are_not_observations(code):
    with pytest.raises(api.PublicDataError):
        api.parse_page(json_page(code=code))


def test_explicit_no_data_code_and_service_specific_success_code():
    no_data = b'{"response":{"header":{"resultCode":"03"}}}'
    with pytest.raises(api.PublicDataError):
        api.parse_page(no_data)
    result = api.parse_page(no_data, no_data_codes=("03",))
    assert result.items == []
    assert result.total_count == 0
    assert result.meta["explicit_no_data"] is True
    result = api.parse_page(json_page(code="000"), success_codes=("000",))
    assert result.meta["result_code"] == "000"


@pytest.mark.parametrize("field", ["totalCount", "body", "header"])
def test_required_envelope_fields_cannot_be_silently_replaced(field):
    payload = json.loads(json_page())
    if field == "totalCount":
        del payload["response"]["body"][field]
    else:
        del payload["response"][field]
    with pytest.raises(api.ResponseSchemaError):
        api.parse_page(json.dumps(payload).encode())


@pytest.mark.parametrize("field,value", [
    ("totalCount", True), ("totalCount", -1), ("totalCount", "1.5"),
    ("pageNo", False), ("pageNo", 2), ("pageNo", "one"),
    ("numOfRows", 0), ("numOfRows", -1), ("numOfRows", True),
])
def test_invalid_server_pagination_is_rejected(field, value):
    payload = json.loads(json_page())
    payload["response"]["body"][field] = value
    with pytest.raises(api.ResponseSchemaError):
        api.parse_page(json.dumps(payload).encode())


@pytest.mark.parametrize("raw,requested_page,requested_size", [
    (json_page([], 0, page=0), 0, 10),
    (json_page([], 0, size=5), 1, 10),
    (json_page([], 1), 1, 10),
    (json_page([{"id": str(n)} for n in range(10)], 11, page=2), 2, 10),
])
def test_pagination_does_not_claim_complete_data_from_inconsistent_pages(raw, requested_page, requested_size):
    with pytest.raises(api.ResponseSchemaError):
        api.parse_page(raw, requested_page=requested_page, requested_size=requested_size)


@pytest.mark.parametrize("items,total,size", [
    ([{"id": "A"}], 0, 10),
    ([{"id": "A"}, {"id": "B"}], 1, 10),
    ([{"id": "A"}, {"id": "B"}], 2, 1),
    (["scalar"], 1, 10),
])
def test_observed_item_count_and_shape_must_match_page(items, total, size):
    with pytest.raises(api.ResponseSchemaError):
        api.parse_page(json_page(items, total, size=size), requested_size=size)


@pytest.mark.parametrize("raw", [b"not JSON or XML", b"[]", b"{invalid", b"<response>", b"\xff\xfe", b'<!DOCTYPE response [<!ENTITY x "secret">]><response>&x;</response>'])
def test_invalid_or_unsafe_payload_is_rejected(raw):
    with pytest.raises(api.ResponseSchemaError):
        api.parse_page(raw)


@pytest.mark.parametrize("endpoint", [
    "http://apis.data.go.kr/service", "https://evil.example/service",
    "https://apis.data.go.kr.evil.example/service", "https://evil.example/apis.data.go.kr/service",
    "https://user:pass@apis.data.go.kr/service", "https://apis.data.go.kr/service?serviceKey=bad",
    "https://apis.data.go.kr/service#fragment", "https://apis.data.go.kr/a/../service",
    "https://apis.data.go.kr:8443/service", "https://apis.data.go.kr:0/service",
])
def test_endpoint_must_be_official_https_host_without_credentials_or_query(endpoint):
    with pytest.raises(api.PublicDataError):
        api.validate_endpoint(endpoint)


def test_valid_official_endpoint_is_allowed():
    assert api.validate_endpoint(ENDPOINT) is None


@pytest.mark.parametrize("field", ["serviceKey", "service_key", "api-key", "Authorization", "password", "authToken"])
def test_user_parameters_cannot_supply_authentication(field):
    with pytest.raises(api.PublicDataError):
        api.safe_parameters({field: "not-a-real-key"})


@pytest.mark.parametrize("supplied_key", [TEST_KEY, quote(TEST_KEY, safe="")])
def test_service_key_is_url_encoded_exactly_once(supplied_key):
    opener = ScriptedOpener(json_page())
    client = api.PublicDataClient(supplied_key, opener=opener, sleep=lambda value: None)
    parameters = {"pageNo": 1, "numOfRows": 10, "type": "json"}
    original = dict(parameters)
    page, raw = client.fetch(ENDPOINT, parameters)
    request, timeout = opener.calls[0]
    query = urlsplit(request.full_url).query
    assert parse_qs(query)["serviceKey"] == [TEST_KEY]
    assert query.count("serviceKey=") == 1
    assert "serviceKey=" + quote_plus(TEST_KEY) in query
    assert parameters == original
    assert timeout == 20
    assert page.items == []
    assert raw == json_page()


def test_environment_loader_and_client_do_not_double_decode_literal_percent(monkeypatch, tmp_path):
    raw_key = "synthetic+literal%2B/="
    monkeypatch.setenv(api.CREDENTIAL_NAME, quote(raw_key, safe=""))
    # ENV 설정으로 분기하므로 tmp_path 안의 .env조차 만들거나 읽지 않는다.
    loaded = api.load_service_key(root=tmp_path)
    opener = ScriptedOpener(json_page())
    api.PublicDataClient(loaded, opener=opener).fetch(ENDPOINT, {})
    query = parse_qs(urlsplit(opener.calls[0][0].full_url).query)
    assert query["serviceKey"] == [raw_key]


def test_redaction_covers_raw_encoded_and_twice_encoded_key():
    variants = [TEST_KEY, quote(TEST_KEY, safe=""), quote(quote(TEST_KEY, safe=""), safe="")]
    result = api.redact_text(" | ".join(variants), TEST_KEY)
    assert result.count("[REDACTED]") == len(variants)
    assert all(variant not in result for variant in variants)


@pytest.mark.parametrize("dataset,allowed", [("facilities", "bzentyNm"), ("contracts", "cntrctNm")])
def test_snapshot_privacy_whitelist_drops_contacts_unknown_and_nested_fields(dataset, allowed):
    page = api.Page([{
        allowed: "public facility " + TEST_KEY,
        "ofclNm": "private person", "rprsntvNm": "private representative",
        "telNo": "010-private", "email": "private@example.org", "serviceKey": TEST_KEY,
        "corpList": [{"name": "private person"}], "unknownField": "unreviewed",
    }], 1, 1, 10, {"format": "json"})
    snapshot = api.public_snapshot(page, dataset, TEST_KEY)
    assert snapshot["items"] == [{allowed: "public facility [REDACTED]"}]
    serialized = json.dumps(snapshot, ensure_ascii=False)
    assert TEST_KEY not in serialized
    assert "private person" not in serialized
    assert "private@example.org" not in serialized
    assert "unreviewed" not in serialized
    assert set(snapshot["excluded_fields"]) == {"ofclNm", "rprsntvNm", "telNo", "email", "serviceKey", "corpList", "unknownField"}


def test_whitelisted_field_with_nested_payload_is_excluded():
    page = api.Page([{"bzentyNm": {"contact": "private"}, "bzentyId": "A"}], 1, 1, 10)
    snapshot = api.public_snapshot(page, "facilities", TEST_KEY)
    assert snapshot["items"] == [{"bzentyId": "A"}]
    assert "bzentyNm" in snapshot["excluded_fields"]


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_http_error_retries_with_backoff(status, monkeypatch):
    monkeypatch.setattr(api.time, "monotonic", lambda: 100.0)
    sleeps = []
    error = HTTPError(ENDPOINT, status, "transient " + TEST_KEY, {}, None)
    opener = ScriptedOpener(error, json_page())
    client = api.PublicDataClient(TEST_KEY, opener=opener, sleep=sleeps.append, retries=2, interval=.35)
    page, _ = client.fetch(ENDPOINT, {})
    assert page.items == []
    assert len(opener.calls) == 2
    assert 1 in sleeps
    assert .35 in sleeps


@pytest.mark.parametrize("error", [URLError("network " + TEST_KEY), TimeoutError(TEST_KEY), OSError(TEST_KEY)])
def test_transient_connection_error_retries(error):
    sleeps = []
    opener = ScriptedOpener(error, json_page())
    client = api.PublicDataClient(TEST_KEY, opener=opener, sleep=sleeps.append, interval=0, retries=1)
    assert client.fetch(ENDPOINT, {})[0].items == []
    assert len(opener.calls) == 2
    assert 1 in sleeps


def test_nonretryable_http_authentication_error_does_not_retry_or_expose_key(capsys, caplog):
    opener = ScriptedOpener(HTTPError(ENDPOINT + "?serviceKey=" + TEST_KEY, 403, "secret " + TEST_KEY, {}, None))
    sleeps = []
    client = api.PublicDataClient(TEST_KEY, opener=opener, sleep=sleeps.append, retries=4)
    with pytest.raises(api.PublicDataError, match="403") as error:
        client.fetch(ENDPOINT, {})
    assert len(opener.calls) == 1
    assert sleeps == []
    assert TEST_KEY not in str(error.value)
    captured = capsys.readouterr()
    assert TEST_KEY not in captured.out + captured.err + caplog.text


def test_connection_retry_exhaustion_is_bounded_and_sanitized():
    opener = ScriptedOpener(*(URLError("network " + TEST_KEY) for _ in range(3)))
    sleeps = []
    client = api.PublicDataClient(TEST_KEY, opener=opener, sleep=sleeps.append, retries=2, interval=0)
    with pytest.raises(api.PublicDataError, match="연결") as error:
        client.fetch(ENDPOINT, {})
    assert len(opener.calls) == 3
    assert [value for value in sleeps if value >= 1] == [1, 2]
    assert TEST_KEY not in str(error.value)


def test_http_retry_exhaustion_preserves_status_without_server_reason():
    opener = ScriptedOpener(*(HTTPError(ENDPOINT, 503, "server secret " + TEST_KEY, {}, None) for _ in range(2)))
    client = api.PublicDataClient(TEST_KEY, opener=opener, sleep=lambda value: None, retries=1, interval=0)
    with pytest.raises(api.PublicDataError, match="503") as error:
        client.fetch(ENDPOINT, {})
    assert len(opener.calls) == 2
    assert TEST_KEY not in str(error.value)


def test_service_error_is_not_retried_as_a_network_failure():
    opener = ScriptedOpener(json_page(code="07"))
    client = api.PublicDataClient(TEST_KEY, opener=opener, sleep=lambda value: None, retries=5)
    with pytest.raises(api.PublicDataError):
        client.fetch(ENDPOINT, {})
    assert len(opener.calls) == 1


def test_twenty_megabyte_response_limit_is_enforced_at_read_and_decode():
    assert api.MAX_RESPONSE_BYTES == 20_000_000
    raw = b" " * (api.MAX_RESPONSE_BYTES + 1)
    opener = ScriptedOpener(raw)
    client = api.PublicDataClient(TEST_KEY, opener=opener, sleep=lambda value: None)
    with pytest.raises(api.ResponseSchemaError, match="크기"):
        client.fetch(ENDPOINT, {})
    assert opener.responses[0].read_limits == [api.MAX_RESPONSE_BYTES + 1]
    assert len(opener.calls) == 1


def test_exact_maximum_sized_valid_payload_is_allowed():
    payload = json_page()
    padded = payload + b" " * (api.MAX_RESPONSE_BYTES - len(payload))
    assert api.parse_page(padded).items == []


@pytest.mark.parametrize("field,value", [
    ("retries", True), ("retries", -1), ("retries", 6), ("retries", 1.5),
    ("timeout", True), ("timeout", 0), ("timeout", 121), ("timeout", float("nan")), ("timeout", float("inf")),
    ("interval", False), ("interval", -.1), ("interval", 61), ("interval", float("nan")), ("interval", float("inf")),
])
def test_client_rejects_invalid_retry_timeout_and_interval_limits(field, value):
    with pytest.raises(ValueError):
        api.PublicDataClient(TEST_KEY, **{field: value})


@pytest.mark.parametrize("field,value", [
    ("pageNo", True), ("pageNo", 0), ("pageNo", -1), ("pageNo", 1.5),
    ("numOfRows", True), ("numOfRows", 0), ("numOfRows", -1), ("numOfRows", 1.5),
])
def test_invalid_request_pagination_is_rejected_before_http_request(field, value):
    opener = ScriptedOpener(json_page())
    client = api.PublicDataClient(TEST_KEY, opener=opener, sleep=lambda value: None)
    with pytest.raises((api.PublicDataError, ValueError)):
        client.fetch(ENDPOINT, {field: value})
    assert opener.calls == []


@pytest.mark.parametrize("requested_page,requested_size", [(True, 10), (1, True)])
def test_parse_page_does_not_accept_boolean_request_pagination(requested_page, requested_size):
    with pytest.raises(api.ResponseSchemaError):
        api.parse_page(json_page(size=1 if requested_size is True else 10), requested_page=requested_page, requested_size=requested_size)


def test_redirect_cannot_move_service_key_to_a_different_host():
    request = api.Request(ENDPOINT + "?serviceKey=" + quote_plus(TEST_KEY))
    with pytest.raises(api.PublicDataError):
        api.SameHostRedirect().redirect_request(request, None, 302, "redirect", {}, "https://evil.example/collect?serviceKey=" + quote_plus(TEST_KEY))
