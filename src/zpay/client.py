"""Server-side Z.PAY client. No automatic retry or currency conversion."""
from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Mapping
from typing import Any, TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DEFAULT_BASE_URL = "https://zpaysolution.com/api/v1"
MAX_RESPONSE = 2 * 1024 * 1024
Transport = Callable[[str, str, dict[str, str], bytes | None, float], tuple[int, Mapping[str, str], bytes]]
# BEGIN RESOURCE_TYPES
if TYPE_CHECKING:
    from .resources import AccountService, PaymentsService, DonationsService, CheckoutsService, WithdrawalsService, CashoutsService, RefundsService, TransfersService, BoletosService, BillPaymentsService, MedsService, CryptoService, SubaccountsService, SplitsService
# END RESOURCE_TYPES


class ZPayError(Exception):
    def __init__(self, message: str, *, status: int = 0, code: str = "ZPAY_ERROR",
                 details: Any = None, retry_after: str | None = None, outcome_unknown: bool = False):
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details
        self.retry_after = retry_after
        self.outcome_unknown = outcome_unknown


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _transport(method, url, headers, payload, timeout):
    request = Request(url, data=payload, headers=headers, method=method)
    try:
        response = build_opener(_NoRedirect()).open(request, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read(MAX_RESPONSE + 1)
        return response.status, dict(response.headers.items()), raw


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or value in (".", ".."):
        raise ValueError("Informe um identificador válido.")
    return quote(value, safe="")


def _keyed(data: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    key = data.get(field)
    if not isinstance(key, str) or not key.strip() or len(key) > 120:
        raise ValueError(f"Informe {field} estável, com até 120 caracteres.")
    if field == "requestId" and not re.fullmatch(r"[a-zA-Z0-9_:.-]{8,120}", key):
        raise ValueError("requestId deve ter de 8 a 120 caracteres válidos.")
    return data


class ZPay:
    # BEGIN RESOURCE_FIELDS
    account: AccountService
    payments: PaymentsService
    donations: DonationsService
    checkouts: CheckoutsService
    withdrawals: WithdrawalsService
    cashouts: CashoutsService
    refunds: RefundsService
    transfers: TransfersService
    boletos: BoletosService
    bill_payments: BillPaymentsService
    meds: MedsService
    crypto: CryptoService
    subaccounts: SubaccountsService
    splits: SplitsService
    # END RESOURCE_FIELDS
    def __init__(self, client_id: str, client_secret: str, *, base_url: str = DEFAULT_BASE_URL,
                 timeout: float = 30.0, transport: Transport | None = None):
        for value in (client_id, client_secret):
            if not isinstance(value, str) or not value.strip() or "\r" in value or "\n" in value:
                raise ValueError("Credenciais inválidas.")
        parsed = urlsplit(base_url)
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or (
            parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1"))
        ):
            raise ValueError("Use base_url HTTPS sem credenciais, query ou fragmento; HTTP apenas em localhost.")
        if not isinstance(timeout, (float, int)) or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout deve ser positivo e finito.")
        self.__client_id, self.__client_secret = client_id, client_secret
        self.__base_url, self.__timeout = base_url.rstrip("/"), float(timeout)
        self.__transport = transport or _transport
        from .resources import RESOURCES
        for name, resource in RESOURCES.items():
            setattr(self, name, resource(self))

    def _request(self, method: str, path: str, *, data: Mapping[str, Any] | None = None,
                 query: Mapping[str, Any] | None = None) -> dict[str, Any]:
        params = {}
        for key, value in (query or {}).items():
            if value is None:
                continue
            if not isinstance(value, (str, int, float, bool)) or isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"Filtro inválido: {key}.")
            params[key] = str(value).lower() if isinstance(value, bool) else str(value)
        url = self.__base_url + path + ("?" + urlencode(params) if params else "")
        payload = None if data is None else json.dumps(dict(data), ensure_ascii=False, allow_nan=False).encode("utf-8")
        headers = {"accept": "application/json", "content-type": "application/json",
                   "client-id": self.__client_id, "client-secret": self.__client_secret,
                   "user-agent": "zpay-sdk-python/0.1.0"}
        try:
            status, response_headers, raw = self.__transport(method, url, headers, payload, self.__timeout)
        except (TimeoutError, URLError, OSError):
            raise ZPayError("Falha de conexão ou tempo de resposta esgotado.", code="NETWORK_ERROR", outcome_unknown=method != "GET") from None
        if len(raw) > MAX_RESPONSE:
            raise ZPayError("Resposta excedeu o limite.", status=status, code="INVALID_RESPONSE", outcome_unknown=method != "GET")
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ZPayError("Resposta JSON inválida.", status=status, code="INVALID_RESPONSE", outcome_unknown=method != "GET") from None
        if not isinstance(body, dict):
            raise ZPayError("Formato de resposta inválido.", status=status, code="INVALID_RESPONSE", outcome_unknown=method != "GET")
        if not 200 <= status < 300:
            def redact(value):
                if isinstance(value, str):
                    return value.replace(self.__client_secret, "[redacted]").replace(self.__client_id, "[redacted]")
                if isinstance(value, dict):
                    return {key: redact(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [redact(item) for item in value]
                return value
            safe = redact(body)
            raise ZPayError(safe.get("error") if isinstance(safe.get("error"), str) else f"Erro HTTP {status} na Z.PAY.",
                            status=status, code=safe.get("code") if isinstance(safe.get("code"), str) else "API_ERROR",
                            details=safe, retry_after=next((v for k, v in response_headers.items() if k.lower() == "retry-after"), None),
                            outcome_unknown=method != "GET" and (status >= 500 or status in (408, 409, 429) or 300 <= status < 400))
        return body
