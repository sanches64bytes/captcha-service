# Integração com CaptchaAI

## Guia completo da API e dos módulos de CAPTCHA

## 1. Introdução

CaptchaAI é um serviço de resolução de CAPTCHA acessado por API HTTP.

Embora existam vários tipos de CAPTCHA, a arquitetura da API é bastante uniforme:

```text
Aplicação
    │
    │ 1. Prepara os dados do CAPTCHA
    ▼
CaptchaAI / in.php
    │
    │ 2. Cria uma tarefa
    ▼
task_id
    │
    │ 3. Aplicação consulta a tarefa
    ▼
CaptchaAI / res.php
    │
    ├── CAPCHA_NOT_READY
    │
    └── solução
```

O Quickstart oficial descreve exatamente esse fluxo: enviar o CAPTCHA, receber um ID, consultar o estado da tarefa e finalmente obter o resultado.

A API V1 atualmente lista suporte para:

* reCAPTCHA v2
* Invisible reCAPTCHA v2
* reCAPTCHA v2 Enterprise
* reCAPTCHA v3
* reCAPTCHA v3 Enterprise
* Cloudflare Turnstile
* Cloudflare Challenge
* GeeTest v3
* Normal Captcha
* Grid Image
* BLS Captcha
* CaptchaFox — beta
* Friendly Captcha — beta
* Lemin — beta

O guia de Callback do reCAPTCHA v2 é uma variação de integração do reCAPTCHA v2, e não um `method` separado da API.

---

# 2. Uso autorizado

CAPTCHAs são controles antiabuso e antiautomação.

Esta documentação deve ser aplicada em:

* seus próprios sistemas;
* ambientes de desenvolvimento;
* homologação;
* testes automatizados autorizados;
* páginas de demonstração;
* sistemas nos quais você tenha autorização explícita.

A parte documentada aqui termina, em geral, quando o CaptchaAI retorna a solução. O modo como um token, cookie ou resposta é utilizado pelo sistema protegido depende do provedor e da aplicação.

---

# 3. Conceitos fundamentais

Antes de estudar cada módulo, existem alguns conceitos que aparecem repetidamente.

## 3.1 API Key

Todas as requisições precisam identificar sua conta.

Normalmente:

```python
API_KEY = "SUA_API_KEY"
```

Ela é enviada como:

```python
{"key": API_KEY}
```

Uma chave em formato incorreto produz `ERROR_WRONG_USER_KEY`; uma chave que não existe produz `ERROR_KEY_DOES_NOT_EXIST`. A documentação atual informa que o formato esperado da chave possui 32 caracteres.

---

# 4. Endpoints principais

## 4.1 Criar tarefa

Endpoint:

```text
https://ocr.captchaai.com/in.php
```

Ele recebe os parâmetros correspondentes ao CAPTCHA.

Exemplo conceitual:

```python
response = requests.post(
    "https://ocr.captchaai.com/in.php",
    data={
        "key": API_KEY,
        "method": "...",
        "json": 1,
    },
)
```

Uma criação bem-sucedida normalmente retorna:

```json
{
    "status": 1,
    "request": "123456789"
}
```

`request` nesse momento é o identificador da tarefa.

A própria referência oficial de reCAPTCHA v2 usa esse formato.

---

## 4.2 Consultar tarefa

Endpoint:

```text
https://ocr.captchaai.com/res.php
```

Consulta padrão:

```python
response = requests.get(
    "https://ocr.captchaai.com/res.php",
    params={
        "key": API_KEY,
        "action": "get",
        "id": task_id,
        "json": 1,
    },
)
```

A documentação utiliza `action=get` juntamente com o ID retornado por `in.php`.

---

# 5. `json=1`

É recomendável utilizar:

```python
"json": 1
```

Sem ele, algumas respostas são strings como:

```text
OK|123456789
```

ou:

```text
CAPCHA_NOT_READY
```

Com `json=1`:

```json
{
    "status": 0,
    "request": "CAPCHA_NOT_READY"
}
```

ou:

```json
{
    "status": 1,
    "request": "SOLUCAO"
}
```

A documentação de erros recomenda JSON justamente para facilitar o tratamento programático.

---

# 6. Polling

A criação da tarefa e a resolução são operações diferentes.

Por isso não faça:

```python
task = create_task()

print(task["solution"])
```

O resultado provavelmente ainda não estará pronto.

O padrão é:

```python
task_id = create_task()

while True:
    result = get_result(task_id)

    if result["status"] == 1:
        break

    time.sleep(5)
```

Quando o serviço responde:

```text
CAPCHA_NOT_READY
```

isso significa somente:

> a tarefa existe, mas ainda está sendo processada.

A documentação recomenda aproximadamente cinco segundos entre consultas quando esse estado é retornado.

---

# 7. Cliente base em Python

Uma implementação reutilizável pode começar assim:

```python
from __future__ import annotations

import time
from typing import Any

import requests


class CaptchaAIError(Exception):
    pass


class CaptchaAIClient:
    BASE_URL = "https://ocr.captchaai.com"

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()

    def submit(
        self,
        payload: dict[str, Any],
        *,
        files: dict[str, Any] | None = None,
        http_method: str = "POST",
    ) -> str:
        data = {
            "key": self.api_key,
            "json": 1,
            **payload,
        }

        if http_method == "GET":
            response = self.session.get(
                f"{self.BASE_URL}/in.php",
                params=data,
                timeout=self.timeout,
            )
        else:
            response = self.session.post(
                f"{self.BASE_URL}/in.php",
                data=data,
                files=files,
                timeout=self.timeout,
            )

        response.raise_for_status()

        result = response.json()

        if result["status"] != 1:
            raise CaptchaAIError(result["request"])

        return str(result["request"])

    def get_result(self, task_id: str) -> dict[str, Any]:
        response = self.session.get(
            f"{self.BASE_URL}/res.php",
            params={
                "key": self.api_key,
                "action": "get",
                "id": task_id,
                "json": 1,
            },
            timeout=self.timeout,
        )

        response.raise_for_status()

        return response.json()

    def wait_result(
        self,
        task_id: str,
        *,
        interval: float = 5,
        timeout: float = 120,
    ) -> dict[str, Any]:
        started_at = time.monotonic()

        while True:
            result = self.get_result(task_id)

            if result["status"] == 1:
                return result

            error = result["request"]

            if error != "CAPCHA_NOT_READY":
                raise CaptchaAIError(error)

            if time.monotonic() - started_at >= timeout:
                raise TimeoutError(f"CaptchaAI task {task_id} timed out.")

            time.sleep(interval)
```

A arquitetura acima reproduz o fluxo oficial `in.php → task_id → res.php`, acrescentando timeout e tratamento centralizado de erros.

---

# 8. Normal Captcha

## O que é

É o CAPTCHA tradicional baseado em uma imagem contendo texto ou números distorcidos.

Fluxo:

```text
imagem
  ↓
CaptchaAI
  ↓
"ABC123"
```

O CaptchaAI aceita atualmente JPG, JPEG, PNG e GIF. A documentação informa tamanho entre 100 bytes e 100 KB para esse módulo.

## Parâmetros principais

```text
key
method=post
json=1
file=<imagem>
```

## Exemplo

```python
with open("captcha.png", "rb") as captcha:
    task_id = client.submit(
        {
            "method": "post",
        },
        files={
            "file": captcha,
        },
    )

result = client.wait_result(task_id)

text = result["request"]
```

O `method` utilizado pela documentação oficial para CAPTCHA de imagem é `post`.

## Resultado

Exemplo:

```json
{
    "status": 1,
    "request": "ABC123"
}
```

Nesse módulo:

```text
request = texto reconhecido
```

## Opções adicionais

A documentação também menciona:

```text
regsense=1
```

para CAPTCHAs sensíveis a maiúsculas/minúsculas, e:

```text
numeric=1
```

quando a imagem contém apenas números.

---

# 9. Grid Image

## O que é

É um CAPTCHA contendo uma grade, normalmente:

```text
1 2 3
4 5 6
7 8 9
```

ou:

```text
 1  2  3  4
 5  6  7  8
 9 10 11 12
13 14 15 16
```

A tarefa contém:

* imagem completa;
* tamanho da grade;
* instrução;
* tipo da imagem.

A resposta contém os índices das células correspondentes.

## Parâmetros

```text
method=post
grid_size
img_type
instructions
file
```

Exemplo:

```python
with open("grid.png", "rb") as image:
    task_id = client.submit(
        {
            "method": "post",
            "grid_size": "3x3",
            "img_type": "recaptcha",
            "instructions": "bicycles",
        },
        files={
            "file": image,
        },
    )
```

Esse formato corresponde ao exemplo atual da documentação.

## Resultado

O campo `request` contém uma string JSON:

```json
{
    "status": 1,
    "request": "[1, 3, 6, 9]"
}
```

Portanto:

```python
import json

result = client.wait_result(task_id)

cells = json.loads(result["request"])
```

Agora:

```python
cells == [1, 3, 6, 9]
```

A numeração ocorre da esquerda para a direita e de cima para baixo.

---

# 10. reCAPTCHA v2

## O que é

É o reCAPTCHA clássico do Google.

O CaptchaAI precisa principalmente de:

```text
sitekey
pageurl
```

Na API, a `sitekey` do Google recebe o nome:

```text
googlekey
```

O método é:

```text
userrecaptcha
```

A referência oficial usa `method=userrecaptcha`, `googlekey` e `pageurl`.

## Payload

```python
task_id = client.submit(
    {
        "method": "userrecaptcha",
        "googlekey": SITE_KEY,
        "pageurl": PAGE_URL,
    },
)
```

## Resultado

```json
{
    "status": 1,
    "request": "TOKEN..."
}
```

Nesse módulo:

```text
request = token reCAPTCHA
```

A documentação atual apresenta esse token como a solução da tarefa.

---

# 11. Invisible reCAPTCHA v2

## O que muda

É praticamente o mesmo protocolo do reCAPTCHA v2.

A diferença importante é:

```text
invisible=1
```

A documentação define o fluxo com:

```text
method=userrecaptcha
googlekey=...
pageurl=...
invisible=1
```

## Exemplo

```python
task_id = client.submit(
    {
        "method": "userrecaptcha",
        "googlekey": SITE_KEY,
        "pageurl": PAGE_URL,
        "invisible": 1,
    },
)
```

## Resultado

Assim como no v2:

```text
token
```

A diferença está na configuração da tarefa, não no conceito do resultado.

---

# 12. reCAPTCHA v2 Callback

Este módulo precisa ser entendido de forma diferente.

Não existe:

```text
method=recaptcha_callback
```

A tarefa enviada ao CaptchaAI continua sendo:

```text
method=userrecaptcha
googlekey=...
pageurl=...
```

A documentação oficial confirma que callback-based v2 utiliza o mesmo `in.php`, `method=userrecaptcha` e `res.php` do reCAPTCHA v2 normal.

Então:

```python
task_id = client.submit(
    {
        "method": "userrecaptcha",
        "googlekey": SITE_KEY,
        "pageurl": PAGE_URL,
    },
)
```

O resultado continua sendo:

```text
token
```

O termo **Callback** descreve como determinada aplicação consome esse token, e não um solver diferente dentro do CaptchaAI.

Para aplicações próprias, o token deve ser entregue ao fluxo de validação que seu frontend/backend implementa.

---

# 13. reCAPTCHA v2 Enterprise

## Diferença principal

Continua utilizando:

```text
method=userrecaptcha
```

mas acrescenta:

```text
enterprise=1
```

Também pode existir:

```text
action
```

A documentação atual mostra o seguinte conjunto:

```text
method=userrecaptcha
googlekey
pageurl
enterprise=1
action=<opcional>
json=1
```

## Exemplo

```python
payload = {
    "method": "userrecaptcha",
    "googlekey": SITE_KEY,
    "pageurl": PAGE_URL,
    "enterprise": 1,
}

if action is not None:
    payload["action"] = action

task_id = client.submit(payload)
```

## Resultado

Enterprise é uma exceção importante.

A documentação mostra que a resposta pode ser:

```json
{
    "status": 1,
    "result": "TOKEN...",
    "user_agent": "..."
}
```

em vez do padrão simples:

```json
{
    "status": 1,
    "request": "TOKEN..."
}
```

Por isso o parser não deve presumir que todo solver retorna a solução exclusivamente em `request`.

Uma função útil seria:

```python
def extract_token(result: dict) -> str:
    token = result.get("result") or result.get("request")

    if not token:
        raise CaptchaAIError("Resposta sem token.")

    return token
```

---

# 14. reCAPTCHA v3

## Como ele difere do v2

O v3 é baseado em avaliação de risco e trabalha com uma `action`.

Os principais parâmetros são:

```text
googlekey
pageurl
action
version=v3
```

A documentação atual descreve scores entre `0.1` e `0.9` e destaca que ações diferentes, como login e submit, podem ser tratadas separadamente.

## Payload

```python
task_id = client.submit(
    {
        "method": "userrecaptcha",
        "version": "v3",
        "googlekey": SITE_KEY,
        "action": ACTION,
        "pageurl": PAGE_URL,
    },
)
```

Esse é o formato usado no guia oficial.

## Resultado

```json
{
    "status": 1,
    "request": "TOKEN..."
}
```

---

# 15. reCAPTCHA v3 Enterprise

Aqui combinamos:

```text
v3
+
enterprise
```

## Payload

```python
task_id = client.submit(
    {
        "method": "userrecaptcha",
        "version": "v3",
        "googlekey": SITE_KEY,
        "pageurl": PAGE_URL,
        "enterprise": 1,
        "action": ACTION,
    },
)
```

A documentação oficial especifica `version=v3` juntamente com `enterprise=1`.

## Resultado

Assim como v2 Enterprise, a resposta estruturada pode trazer:

```json
{
    "status": 1,
    "result": "TOKEN...",
    "user_agent": "..."
}
```

A documentação recomenda utilizar `json=1` nesse módulo justamente porque existem campos adicionais na resposta.

---

# 16. GeeTest v3

## Conceitos

GeeTest usa parâmetros diferentes.

Os principais são:

```text
gt
challenge
pageurl
api_server
```

`gt` funciona como identificador público.

`challenge` representa a instância dinâmica do desafio.

`api_server` é opcional.

A documentação alerta que o `challenge` é dinâmico e precisa estar atualizado.

## Payload

```python
task_id = client.submit(
    {
        "method": "geetest",
        "gt": GT,
        "challenge": CHALLENGE,
        "pageurl": PAGE_URL,
        "api_server": API_SERVER,
    },
    http_method="GET",
)
```

O método oficial é:

```text
geetest
```

## Resultado

Aqui não recebemos somente um token.

A resposta possui um JSON serializado dentro de `request`:

```json
{
    "status": 1,
    "request": "{\"challenge\":\"...\",\"validate\":\"...\",\"seccode\":\"...\"}"
}
```

Precisamos fazer:

```python
import json

result = client.wait_result(task_id)

solution = json.loads(result["request"])
```

Agora:

```python
solution["challenge"]
solution["validate"]
solution["seccode"]
```

são os três componentes retornados pelo módulo GeeTest v3.

---

# 17. Cloudflare Turnstile

Turnstile utiliza uma interface semelhante ao reCAPTCHA.

Principais parâmetros:

```text
sitekey
pageurl
```

Método:

```text
turnstile
```

A documentação atual mostra exatamente esses campos.

## Payload

```python
task_id = client.submit(
    {
        "method": "turnstile",
        "sitekey": SITE_KEY,
        "pageurl": PAGE_URL,
    },
    http_method="GET",
)
```

## Resultado

```json
{
    "status": 1,
    "request": "TOKEN..."
}
```

Nesse módulo:

```text
request = Turnstile token
```

Em aplicações próprias, entregue esse valor ao fluxo de validação Turnstile do ambiente de teste ou homologação.

---

# 18. Cloudflare Challenge

Este módulo é diferente de Turnstile.

Turnstile normalmente produz:

```text
token
```

Cloudflare Challenge pode produzir:

```text
cf_clearance
+
User-Agent
```

A documentação descreve esse módulo como a página intermediária de proteção Cloudflare e informa que a solução está vinculada ao contexto da sessão/IP.

O método documentado é:

```text
cloudflare_challenge
```

Esse é um caso em que a documentação oficial também exige contexto de rede consistente.

Para testes autorizados, a criação conceitual da tarefa é:

```python
payload = {
    "method": "cloudflare_challenge",
    "pageurl": PAGE_URL,
}
```

e a resposta estruturada contém informações específicas da sessão.

Não trate esse módulo como Turnstile:

```text
Turnstile
    → token de widget

Cloudflare Challenge
    → estado/cookie de sessão + contexto
```

Por ser uma proteção de acesso, este guia não entra em procedimentos para reutilizar `cf_clearance` ou outros dados contra páginas de terceiros.

---

# 19. BLS Captcha

## Estrutura

BLS utiliza exatamente uma grade:

```text
1 2 3
4 5 6
7 8 9
```

São fornecidas:

* nove imagens;
* uma instrução numérica.

Exemplo:

```text
664
```

A resposta é uma lista de posições.

## Método

```text
bls
```

## Dados

```python
data = {
    "method": "bls",
    "instructions": "664",
}
```

As imagens são enviadas como:

```text
image_base64_1
image_base64_2
...
image_base64_9
```

A documentação atual especifica imagens Base64 em formato data URI.

Exemplo conceitual:

```python
files = {
    f"image_base64_{index + 1}": (None, image) for index, image in enumerate(images)
}
```

com:

```python
len(images) == 9
```

## Resultado

```json
{
    "status": 1,
    "request": "[1, 4, 7, 8]"
}
```

Parse:

```python
import json

result = client.wait_result(task_id)

cells = json.loads(result["request"])
```

Nesse caso:

```python
cells == [1, 4, 7, 8]
```

---

# 20. CaptchaFox

**Status atual: beta.**

CaptchaFox trabalha principalmente com:

```text
sitekey
pageurl
```

O método é:

```text
captchafox
```

A documentação atual também associa esse módulo a contexto de rede e informa que a resposta pode conter o User-Agent do solver.

## Payload básico

Em um ambiente autorizado, a estrutura base da tarefa é:

```python
payload = {
    "method": "captchafox",
    "pageurl": PAGE_URL,
    "sitekey": SITE_KEY,
}
```

## Resultado

A resposta pode ser:

```json
{
    "status": 1,
    "request": "TOKEN...",
    "user_agent": "..."
}
```

O token fica em:

```python
token = result["request"]
```

e dados adicionais devem ser preservados caso o ambiente de testes necessite validar contexto de sessão.

---

# 21. Friendly Captcha

**Status atual: beta.**

Friendly Captcha é baseado em proof-of-work e possui uma `sitekey`.

Principais parâmetros:

```text
method=friendly_captcha
pageurl
sitekey
```

A documentação mostra a `sitekey` no atributo `data-sitekey` do widget `frc-captcha`.

## Payload

```python
task_id = client.submit(
    {
        "method": "friendly_captcha",
        "pageurl": PAGE_URL,
        "sitekey": SITE_KEY,
    },
    http_method="GET",
)
```

Esse é exatamente o conjunto principal de parâmetros especificado atualmente.

## Resultado

```json
{
    "status": 1,
    "request": "TOKEN..."
}
```

Portanto:

```python
result = client.wait_result(task_id)

token = result["request"]
```

---

# 22. Lemin

**Status atual: beta.**

Lemin não utiliza simplesmente uma `sitekey`.

O principal identificador é:

```text
captcha_id
```

Também pode existir:

```text
div_id
```

A documentação cita ainda `challenge_id` como informação que pode aparecer na implementação.

## Método

```text
lemin
```

## Payload

```python
payload = {
    "method": "lemin",
    "pageurl": PAGE_URL,
    "captcha_id": CAPTCHA_ID,
}

if div_id:
    payload["div_id"] = div_id

task_id = client.submit(
    payload,
    http_method="GET",
)
```

O formato está alinhado ao exemplo atual da documentação oficial.

## Resultado

```json
{
    "status": 1,
    "request": "lemin-solution-token"
}
```

Portanto:

```python
token = result["request"]
```

---

# 23. Resumo dos métodos

A melhor maneira de memorizar a API é esta:

```text
Normal
method=post

Grid Image
method=post

reCAPTCHA v2
method=userrecaptcha

reCAPTCHA v2 Invisible
method=userrecaptcha
invisible=1

reCAPTCHA v2 Callback
method=userrecaptcha
# callback não é um solver separado

reCAPTCHA v2 Enterprise
method=userrecaptcha
enterprise=1

reCAPTCHA v3
method=userrecaptcha
version=v3

reCAPTCHA v3 Enterprise
method=userrecaptcha
version=v3
enterprise=1

GeeTest v3
method=geetest

Turnstile
method=turnstile

Cloudflare Challenge
method=cloudflare_challenge

BLS
method=bls

CaptchaFox
method=captchafox

Friendly Captcha
method=friendly_captcha

Lemin
method=lemin
```

Esses tipos correspondem aos módulos atualmente listados pela referência API V1 e pelos guias oficiais.

---

# 24. Resumo dos resultados

```text
Normal
    → texto

Grid
    → list[int]

reCAPTCHA v2
    → token

Invisible v2
    → token

Callback v2
    → token

v2 Enterprise
    → token + metadados

v3
    → token

v3 Enterprise
    → token + metadados

GeeTest
    → challenge + validate + seccode

Turnstile
    → token

Cloudflare Challenge
    → estado/cookie + metadados de sessão

BLS
    → list[int]

CaptchaFox
    → token + possível User-Agent

Friendly Captcha
    → token

Lemin
    → token
```

Os formatos diferentes são importantes para projetar corretamente seu cliente.

---

# 25. Modelando a solução

Em vez de retornar `dict` para toda a aplicação, uma implementação melhor pode criar tipos próprios.

```python
from dataclasses import dataclass


@dataclass
class TokenSolution:
    token: str
    user_agent: str | None = None


@dataclass
class TextSolution:
    text: str


@dataclass
class GridSolution:
    cells: list[int]


@dataclass
class GeetestSolution:
    challenge: str
    validate: str
    seccode: str
```

Dessa maneira:

```text
CaptchaAI HTTP response
        ↓
parser
        ↓
modelo interno
        ↓
restante da aplicação
```

Sua aplicação não precisa conhecer as inconsistências entre:

```text
request
```

e:

```text
result
```

existentes em alguns formatos da API.

---

# 26. Parsers

## Token

```python
def parse_token(result: dict) -> TokenSolution:
    token = result.get("result") or result.get("request")

    if not isinstance(token, str):
        raise CaptchaAIError("Token inválido.")

    return TokenSolution(
        token=token,
        user_agent=result.get("user_agent"),
    )
```

## Grid

```python
import json


def parse_grid(result: dict) -> GridSolution:
    cells = json.loads(result["request"])

    if not isinstance(cells, list):
        raise CaptchaAIError("Grid inválido.")

    return GridSolution(
        cells=[int(cell) for cell in cells],
    )
```

## GeeTest

```python
def parse_geetest(result: dict) -> GeetestSolution:
    data = json.loads(result["request"])

    return GeetestSolution(
        challenge=data["challenge"],
        validate=data["validate"],
        seccode=data["seccode"],
    )
```

---

# 27. Tratamento de erros

A documentação oficial separa os erros em:

```text
in.php
```

e:

```text
res.php
```

## Erros importantes

### `ERROR_WRONG_USER_KEY`

API key em formato incorreto.

Não adianta repetir a mesma request.

```text
→ corrigir configuração
```

### `ERROR_KEY_DOES_NOT_EXIST`

A chave não existe.

```text
→ verificar API key
```

### `ERROR_ZERO_BALANCE`

Saldo/threads insuficientes para aceitar outra tarefa.

```text
→ não é erro do CAPTCHA
```

### `ERROR_PAGEURL`

Um módulo que exige `pageurl` não recebeu o parâmetro corretamente.

```text
→ corrigir payload
```

### `ERROR_BAD_PARAMETERS`

Payload incompleto ou tipos de parâmetros incorretos.

```text
→ validar antes de enviar
```

### `CAPCHA_NOT_READY`

Não é uma falha.

Significa:

```text
tarefa ainda processando
```

Ação:

```text
esperar
↓
consultar novamente
```

A documentação recomenda aproximadamente cinco segundos.

### `ERROR_CAPTCHA_UNSOLVABLE`

O serviço não conseguiu produzir uma solução após as tentativas de resolução.

Nesse caso:

```text
tarefa terminou sem solução
```

### `ERROR_WRONG_ID_FORMAT`

ID enviado ao `res.php` possui formato inválido.

### `ERROR_WRONG_CAPTCHA_ID`

O ID consultado não corresponde a uma tarefa válida.

### Erros internos

A documentação inclui:

```text
ERROR_SERVER_ERROR
ERROR_INTERNAL_SERVER_ERROR
```

como erros transitórios e recomenda nova tentativa com espera/backoff.

---

# 28. Classificação dos erros

Uma arquitetura mais robusta deveria separar:

```python
class CaptchaAIError(Exception):
    pass


class CaptchaAIConfigurationError(CaptchaAIError):
    pass


class CaptchaAITemporaryError(CaptchaAIError):
    pass


class CaptchaAIUnsolvableError(CaptchaAIError):
    pass
```

Então:

```python
CONFIG_ERRORS = {
    "ERROR_WRONG_USER_KEY",
    "ERROR_KEY_DOES_NOT_EXIST",
    "ERROR_PAGEURL",
    "ERROR_BAD_PARAMETERS",
}

TEMPORARY_ERRORS = {
    "ERROR_SERVER_ERROR",
    "ERROR_INTERNAL_SERVER_ERROR",
}

UNSOLVABLE_ERRORS = {
    "ERROR_CAPTCHA_UNSOLVABLE",
}
```

Isso permite políticas diferentes.

```text
erro de configuração
    → não repetir automaticamente

erro temporário
    → retry com backoff

não resolvido
    → terminar tarefa ou criar nova conforme regra do sistema

CAPCHA_NOT_READY
    → continuar polling
```

Essa classificação é uma forma de implementar as recomendações de tratamento fornecidas pela própria documentação.

---

# 29. Backoff

Evite:

```python
while True:
    result = get_result()
```

Isso pode gerar centenas de requisições em poucos segundos.

Prefira:

```python
time.sleep(5)
```

entre polls normais.

Para falhas transitórias:

```text
5 s
10 s
20 s
40 s
```

até um limite.

A documentação recomenda polling em torno de cinco segundos para `CAPCHA_NOT_READY` e backoff para erros temporários.

---

# 30. Timeout global

Nunca deixe uma tarefa rodando indefinidamente.

Exemplo:

```python
def wait_result(
    task_id: str,
    timeout: float = 120,
):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        ...

    raise TimeoutError()
```

Seu timeout é uma regra da aplicação; ele impede que indisponibilidade ou erro de integração deixe processos presos.

---

# 31. Organização recomendada

Uma biblioteca dedicada pode ter:

```text
captchaai/
├── __init__.py
├── client.py
├── exceptions.py
├── models.py
├── parsers.py
└── solvers/
    ├── __init__.py
    ├── normal.py
    ├── grid.py
    ├── recaptcha.py
    ├── geetest.py
    ├── turnstile.py
    ├── bls.py
    ├── captchafox.py
    ├── friendly.py
    └── lemin.py
```

`client.py` conhece:

```text
HTTP
in.php
res.php
API key
polling
timeouts
```

Os solvers conhecem:

```text
method
parâmetros
parser da resposta
```

A aplicação conhece apenas:

```text
solver.solve(...)
```

---

# 32. Interface comum

Uma abstração possível:

```python
from typing import Protocol


class Solver(Protocol):
    def submit(self, client: CaptchaAIClient) -> str: ...
```

Exemplo:

```python
from dataclasses import dataclass


@dataclass
class RecaptchaV2:
    sitekey: str
    pageurl: str

    def submit(
        self,
        client: CaptchaAIClient,
    ) -> str:
        return client.submit(
            {
                "method": "userrecaptcha",
                "googlekey": self.sitekey,
                "pageurl": self.pageurl,
            },
        )
```

Uso:

```python
solver = RecaptchaV2(
    sitekey="...",
    pageurl="...",
)

task_id = solver.submit(client)
result = client.wait_result(task_id)
solution = parse_token(result)
```

---

# 33. Segurança da API Key

Nunca coloque:

```python
API_KEY = "..."
```

diretamente no repositório.

Prefira variável de ambiente:

```text
CAPTCHAAI_API_KEY=...
```

e:

```python
import os

API_KEY = os.environ["CAPTCHAAI_API_KEY"]
```

Também evite logar a chave:

```python
logger.info(payload)
```

se `payload` contiver:

```text
key
```

Uma forma melhor:

```python
safe_payload = {key: value for key, value in payload.items() if key != "key"}
```

---

# 34. Concorrência

Cada CAPTCHA corresponde a uma tarefa independente:

```text
captcha A → task 100
captcha B → task 101
captcha C → task 102
```

Por isso o identificador retornado pelo `in.php` deve ser persistido corretamente.

Não faça:

```python
last_task_id = ...
```

como estado global.

Prefira associá-lo ao seu próprio job:

```text
job_id
captcha_type
captchaai_task_id
status
created_at
finished_at
```

A referência da API também expõe conceitos de saldo e uso de threads, e `ERROR_ZERO_BALANCE` pode refletir insuficiência de saldo ou capacidade de threads.

---

# 35. Estados internos recomendados

Seu sistema pode definir:

```text
PENDING
SUBMITTED
PROCESSING
SOLVED
FAILED
TIMEOUT
```

Fluxo:

```text
PENDING
   ↓
SUBMITTED
   ↓
PROCESSING
   ├──→ SOLVED
   ├──→ FAILED
   └──→ TIMEOUT
```

Não use diretamente:

```text
CAPCHA_NOT_READY
```

como estado de domínio.

Ele é um detalhe do CaptchaAI.

Converta:

```text
CAPCHA_NOT_READY
    ↓
PROCESSING
```

---

# 36. Interface unificada de alto nível

Um serviço final poderia oferecer:

```python
class CaptchaService:
    def solve_recaptcha_v2(...):
        ...

    def solve_recaptcha_v3(...):
        ...

    def solve_turnstile(...):
        ...

    def solve_normal(...):
        ...

    def solve_grid(...):
        ...
```

Porém, em aplicações grandes, é melhor separar criação e consulta:

```python
task = captcha_service.submit(...)

# posteriormente

solution = captcha_service.result(task)
```

porque a própria API CaptchaAI é assíncrona.

---

# 37. Fluxo arquitetural completo

```text
┌─────────────────────────┐
│     Sua aplicação       │
└────────────┬────────────┘
             │
             │ CaptchaRequest
             ▼
┌─────────────────────────┐
│      CaptchaService     │
│                         │
│ identifica solver       │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│       Solver            │
│                         │
│ cria payload específico │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│    CaptchaAIClient      │
│                         │
│ POST/GET in.php         │
└────────────┬────────────┘
             │
             ▼
         task_id
             │
             ▼
┌─────────────────────────┐
│ Polling / fila / job    │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│       res.php           │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│        Parser           │
└────────────┬────────────┘
             │
             ▼
      CaptchaSolution
```

Essa arquitetura acompanha naturalmente o protocolo em duas etapas documentado pelo CaptchaAI.

---

# 38. Mapa mental final

Se você entender este mapa, já entende a maior parte do CaptchaAI:

```text
               CaptchaAI
                   │
          ┌────────┴────────┐
          │                 │
       in.php            res.php
          │                 │
      cria tarefa       consulta tarefa
          │                 │
       task_id      CAPCHA_NOT_READY
                            │
                            └── solução
```

E cada solver basicamente só muda o payload:

```text
Normal
    imagem

Grid
    imagem + instrução

reCAPTCHA v2
    googlekey + pageurl

Invisible
    googlekey + pageurl + invisible

v2 Enterprise
    googlekey + pageurl + enterprise

v3
    googlekey + pageurl + action + version

v3 Enterprise
    googlekey + pageurl + action + version + enterprise

GeeTest
    gt + challenge + pageurl

Turnstile
    sitekey + pageurl

Cloudflare Challenge
    pageurl + contexto de sessão autorizado

BLS
    9 imagens + instructions

CaptchaFox
    sitekey + pageurl + contexto necessário

Friendly
    sitekey + pageurl

Lemin
    captcha_id + pageurl
```

Enquanto os resultados pertencem principalmente a quatro categorias:

```text
texto
token
lista de células
estrutura/estado de sessão
```

A lista de módulos e esses formatos estão refletidos na documentação oficial atual da API V1 e nos respectivos guias.

---

# 39. Conclusão

A maior dificuldade do CaptchaAI não está na comunicação HTTP.

O protocolo principal é pequeno:

```text
1. montar payload
2. enviar para in.php
3. receber task_id
4. consultar res.php
5. interpretar CAPCHA_NOT_READY
6. obter resultado
7. converter resultado para um modelo interno
```

O que realmente varia entre módulos é:

```text
method
+
parâmetros de entrada
+
formato da solução
```

Por isso uma implementação sólida não deve criar quinze clientes HTTP diferentes.

Crie:

```text
1 CaptchaAIClient
        +
N solvers
        +
N parsers
```

Assim o código HTTP, autenticação, polling, timeout, retries e tratamento de erros ficam centralizados, enquanto cada módulo é responsável somente pelos dados específicos do seu CAPTCHA.

Esse desenho acompanha diretamente a arquitetura documentada atualmente pelo CaptchaAI.
