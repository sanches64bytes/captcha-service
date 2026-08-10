# Guia de integração da API de CAPTCHAs

Este guia explica como integrar uma aplicação cliente à API de tarefas de
CAPTCHA. A API recebe uma solicitação, inicia o processamento em segundo plano e
devolve imediatamente um identificador chamado `task_id`.

> Utilize a API somente em sistemas próprios, ambientes de teste ou páginas nas
> quais você tenha autorização explícita.

## Visão geral

O processamento é assíncrono. Portanto, a criação da tarefa e a obtenção da
solução acontecem em requisições diferentes:

```text
Aplicação cliente
      │
      │ POST /api/v1/tasks/
      ▼
Recebe task_id e status processing
      │
      │ GET /api/v1/tasks/{task_id}/
      ▼
processing → completed ou failed
```

Não mantenha a requisição `POST` aberta esperando a solução. Depois de receber
o `task_id`, consulte periodicamente a rota de detalhes.

## Endereço base

Nos exemplos deste documento será utilizado:

```text
https://api.seudominio.com
```

Substitua esse endereço pela URL fornecida para o seu ambiente.

Todas as requisições precisam informar uma chave ativa no cabeçalho
`X-API-Key`. Também é aceito o formato `Authorization: Bearer <chave>`.

```http
X-API-Key: <sua-chave-de-api>
```

A chave possui um limite de threads simultâneas. Quando esse limite é atingido,
a nova requisição é recusada com HTTP `429`; ela não entra em fila. Uma thread é
liberada quando a tarefa termina com `completed` ou `failed`.

## Consulta rápida no navegador

Uma versão visual e resumida desta documentação está disponível em:

```text
GET /api/v1/captchas/docs/
```

Envie a chave pelo cabeçalho `X-API-Key`. Para abrir diretamente no navegador,
também é possível usar temporariamente:

```text
/api/v1/captchas/docs/?api_key=<sua-chave>
```

O cabeçalho é preferível, pois evita que a chave apareça no histórico e nos
logs de URL.

## Criar uma tarefa

```http
POST /api/v1/tasks/
Content-Type: application/json
X-API-Key: <sua-chave-de-api>
```

O corpo sempre possui esta estrutura:

```json
{
  "captcha_type": "recaptcha_v2",
  "data": {
    "googlekey": "<site-key>",
    "pageurl": "https://sistema-autorizado.example/pagina"
  }
}
```

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `captcha_type` | string | Tipo de CAPTCHA que deve ser processado. |
| `data` | objeto | Parâmetros específicos do tipo escolhido. |

### Resposta

Uma tarefa aceita retorna HTTP `202 Accepted`:

```json
{
  "task_id": "4dd69e6c-781b-49ba-b59d-f3201507121f",
  "status": "processing"
}
```

Armazene o `task_id`. Ele será necessário para todas as consultas posteriores.

## Consultar uma tarefa

```http
GET /api/v1/tasks/{task_id}/
```

Exemplo:

```http
GET /api/v1/tasks/4dd69e6c-781b-49ba-b59d-f3201507121f/
```

### Processando

```json
{
  "task_id": "4dd69e6c-781b-49ba-b59d-f3201507121f",
  "status": "processing"
}
```

### Concluída

```json
{
  "task_id": "4dd69e6c-781b-49ba-b59d-f3201507121f",
  "status": "completed",
  "result": {
    "solution": "token-ou-texto-retornado"
  }
}
```

### Falha

```json
{
  "task_id": "4dd69e6c-781b-49ba-b59d-f3201507121f",
  "status": "failed",
  "error": {
    "code": "captchaai_unsolvable",
    "message": "ERROR_CAPTCHA_UNSOLVABLE"
  }
}
```

## Estados

| Estado | Significado | Ação recomendada |
| --- | --- | --- |
| `processing` | O CAPTCHA está sendo processado. | Consultar novamente. |
| `completed` | A solução está disponível em `result`. | Encerrar o polling. |
| `failed` | O processamento terminou com erro. | Encerrar o polling e tratar `error`. |

A API apresenta a tarefa como `processing` desde o momento em que ela é aceita.
Internamente, o Redis pode utilizar o estado `PENDING` enquanto o worker ainda
não iniciou a execução, mas esse detalhe não é exposto ao cliente.

A transição pública normal é:

```text
processing → completed
           ↘ failed
```

## Polling recomendado

Consulte a tarefa em intervalos regulares, por exemplo, a cada 3 a 5 segundos.
Não faça consultas continuamente sem intervalo.

O cliente também deve definir seu próprio tempo máximo de espera. Um limite de
dois a três minutos costuma ser apropriado, dependendo do fluxo da aplicação.

Exemplo conceitual:

```text
criar tarefa
     ↓
guardar task_id
     ↓
esperar alguns segundos
     ↓
consultar tarefa
     ├── processing → repetir
     ├── completed → usar result
     └── failed → tratar error
```

## Tipos de CAPTCHA

Campos terminados em `?` são opcionais.

### Normal Captcha

```json
{
  "captcha_type": "normal",
  "data": {
    "body": "<imagem-em-base64>",
    "content_type": "image/png",
    "filename": "captcha.png",
    "regsense": 0,
    "numeric": 0
  }
}
```

`body` pode ser Base64 puro ou uma data URI. JPG/JPEG, PNG e GIF são aceitos. A
imagem deve possuir entre 100 bytes e 100 KB.

Resultado:

```json
{"solution": "ABC123"}
```

### Grid Image

```json
{
  "captcha_type": "grid",
  "data": {
    "body": "<imagem-em-base64>",
    "content_type": "image/png",
    "grid_size": "3x3",
    "img_type": "recaptcha",
    "instructions": "bicycles"
  }
}
```

Resultado:

```json
{"solution": [1, 3, 6, 9]}
```

As posições são numeradas da esquerda para a direita e de cima para baixo.

### reCAPTCHA v2

```json
{
  "captcha_type": "recaptcha_v2",
  "data": {
    "googlekey": "<site-key>",
    "pageurl": "https://sistema-autorizado.example/pagina"
  }
}
```

### Invisible reCAPTCHA v2

```json
{
  "captcha_type": "recaptcha_v2_invisible",
  "data": {
    "googlekey": "<site-key>",
    "pageurl": "https://sistema-autorizado.example/pagina"
  }
}
```

### reCAPTCHA v2 Callback

```json
{
  "captcha_type": "recaptcha_v2_callback",
  "data": {
    "googlekey": "<site-key>",
    "pageurl": "https://sistema-autorizado.example/pagina"
  }
}
```

Callback utiliza o mesmo processo de resolução do reCAPTCHA v2. O nome indica
como a aplicação autorizada consumirá o token retornado.

### reCAPTCHA v2 Enterprise

```json
{
  "captcha_type": "recaptcha_v2_enterprise",
  "data": {
    "googlekey": "<site-key>",
    "pageurl": "https://sistema-autorizado.example/pagina",
    "action": "login"
  }
}
```

`action` é opcional no v2 Enterprise.

### reCAPTCHA v3

```json
{
  "captcha_type": "recaptcha_v3",
  "data": {
    "googlekey": "<site-key>",
    "pageurl": "https://sistema-autorizado.example/pagina",
    "action": "login"
  }
}
```

### reCAPTCHA v3 Enterprise

```json
{
  "captcha_type": "recaptcha_v3_enterprise",
  "data": {
    "googlekey": "<site-key>",
    "pageurl": "https://sistema-autorizado.example/pagina",
    "action": "login"
  }
}
```

Os módulos reCAPTCHA retornam normalmente:

```json
{"solution": "<token>"}
```

Respostas Enterprise também podem incluir `user_agent`.

### GeeTest v3

```json
{
  "captcha_type": "geetest_v3",
  "data": {
    "gt": "<gt>",
    "challenge": "<challenge-atual>",
    "pageurl": "https://sistema-autorizado.example/pagina",
    "api_server": "<servidor-opcional>"
  }
}
```

O `challenge` é dinâmico e precisa estar atualizado. Resultado:

```json
{
  "solution": {
    "challenge": "...",
    "validate": "...",
    "seccode": "..."
  }
}
```

### Cloudflare Turnstile

```json
{
  "captcha_type": "turnstile",
  "data": {
    "sitekey": "<site-key>",
    "pageurl": "https://sistema-autorizado.example/pagina"
  }
}
```

### Cloudflare Challenge

```json
{
  "captcha_type": "cloudflare_challenge",
  "data": {
    "pageurl": "https://sistema-autorizado.example/pagina",
    "proxy": "<proxy-opcional>",
    "proxytype": "HTTP",
    "user_agent": "<user-agent-opcional>"
  }
}
```

Esse resultado pode estar associado ao contexto de rede e ao User-Agent. A
aplicação deve preservar os metadados retornados pelo ambiente autorizado.

### BLS Captcha

```json
{
  "captcha_type": "bls",
  "data": {
    "instructions": "664",
    "images": [
      "data:image/png;base64,...",
      "data:image/png;base64,...",
      "data:image/png;base64,...",
      "data:image/png;base64,...",
      "data:image/png;base64,...",
      "data:image/png;base64,...",
      "data:image/png;base64,...",
      "data:image/png;base64,...",
      "data:image/png;base64,..."
    ]
  }
}
```

`images` deve conter exatamente nove data URIs Base64. Resultado:

```json
{"solution": [1, 4, 7, 8]}
```

### CaptchaFox

```json
{
  "captcha_type": "captchafox",
  "data": {
    "sitekey": "<site-key>",
    "pageurl": "https://sistema-autorizado.example/pagina",
    "proxy": "<proxy-opcional>",
    "proxytype": "HTTP"
  }
}
```

### Friendly Captcha

```json
{
  "captcha_type": "friendly_captcha",
  "data": {
    "sitekey": "<site-key>",
    "pageurl": "https://sistema-autorizado.example/pagina"
  }
}
```

### Lemin

```json
{
  "captcha_type": "lemin",
  "data": {
    "captcha_id": "<captcha-id>",
    "pageurl": "https://sistema-autorizado.example/pagina",
    "div_id": "<div-id-opcional>"
  }
}
```

CaptchaFox, Friendly Captcha e Lemin são módulos beta no CaptchaAI.

## Exemplo com cURL

Criar a tarefa:

```bash
curl --request POST 'https://api.seudominio.com/api/v1/tasks/' \
  --header 'X-API-Key: <sua-chave-de-api>' \
  --header 'Content-Type: application/json' \
  --data '{
    "captcha_type": "turnstile",
    "data": {
      "sitekey": "<site-key>",
      "pageurl": "https://sistema-autorizado.example/pagina"
    }
  }'
```

Consultar a tarefa:

```bash
curl --header 'X-API-Key: <sua-chave-de-api>' \
  'https://api.seudominio.com/api/v1/tasks/<task-id>/'
```

## Exemplo completo em Python

```python
import time

import requests


BASE_URL = "https://api.seudominio.com/api/v1"
API_KEY = "<sua-chave-de-api>"


def create_task(captcha_type: str, data: dict) -> str:
    response = requests.post(
        f"{BASE_URL}/tasks/",
        json={"captcha_type": captcha_type, "data": data},
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["task_id"]


def wait_task(task_id: str, timeout: float = 180) -> dict:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        response = requests.get(
            f"{BASE_URL}/tasks/{task_id}/",
            headers={"X-API-Key": API_KEY},
            timeout=30,
        )
        response.raise_for_status()
        task = response.json()

        if task["status"] == "completed":
            return task["result"]

        if task["status"] == "failed":
            error = task["error"]
            raise RuntimeError(f"{error['code']}: {error['message']}")

        time.sleep(5)

    raise TimeoutError(f"Task {task_id} did not finish in time.")


task_id = create_task(
    "recaptcha_v2",
    {
        "googlekey": "<site-key>",
        "pageurl": "https://sistema-autorizado.example/pagina",
    },
)

result = wait_task(task_id)
print(result["solution"])
```

## Exemplo completo em JavaScript

```javascript
const baseUrl = "https://api.seudominio.com/api/v1";
const apiKey = "<sua-chave-de-api>";

const sleep = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

async function createTask(captchaType, data) {
  const response = await fetch(`${baseUrl}/tasks/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body: JSON.stringify({ captcha_type: captchaType, data }),
  });

  if (!response.ok) {
    throw new Error(`Task creation failed with HTTP ${response.status}`);
  }

  return response.json();
}

async function waitTask(taskId, timeoutMs = 180000) {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const response = await fetch(`${baseUrl}/tasks/${taskId}/`, {
      headers: { "X-API-Key": apiKey },
    });

    if (!response.ok) {
      throw new Error(`Task query failed with HTTP ${response.status}`);
    }

    const task = await response.json();

    if (task.status === "completed") return task.result;

    if (task.status === "failed") {
      throw new Error(`${task.error.code}: ${task.error.message}`);
    }

    await sleep(5000);
  }

  throw new Error(`Task ${taskId} did not finish in time.`);
}

const task = await createTask("turnstile", {
  sitekey: "<site-key>",
  pageurl: "https://sistema-autorizado.example/pagina",
});

const result = await waitTask(task.task_id);
console.log(result.solution);
```

## Códigos HTTP

| Código | Significado |
| --- | --- |
| `202` | Tarefa validada, armazenada e enviada para processamento. |
| `200` | Consulta realizada com sucesso. |
| `401` | Chave ausente, inválida ou expirada. |
| `404` | O `task_id` não existe ou já expirou. |
| `422` | Tipo de CAPTCHA ou dados enviados são inválidos. |
| `429` | O limite de threads da chave foi atingido. A tarefa não foi criada. |
| `503` | Não foi possível enviar a tarefa para a fila de processamento. |

Um HTTP `200` na consulta não significa necessariamente que o CAPTCHA foi
resolvido. Sempre verifique o campo `status`.

## Erros de processamento

Quando `status` for `failed`, use `error.code` para decidir o comportamento da
aplicação. Entre os códigos possíveis estão:

| Código | Significado geral |
| --- | --- |
| `captchaai_configuration_error` | Parâmetros ou configuração do provider inválidos. |
| `captchaai_unsolvable` | O provider não conseguiu resolver o CAPTCHA. |
| `captchaai_timeout` | O tempo máximo de processamento foi atingido. |
| `captchaai_http_error` | Falha de comunicação HTTP com o provider. |
| `captchaai_invalid_response` | O provider retornou uma resposta inesperada. |
| `captchaai_temporary_error` | Erro temporário informado pelo provider. |
| `captchaai_provider_error` | Outro erro informado pelo provider. |
| `queue_unavailable` | A tarefa não pôde ser adicionada à fila. |
| `unexpected_error` | Falha interna não classificada. |

Não repita automaticamente erros de configuração. Para falhas temporárias, use
um número limitado de tentativas com espera progressiva.

## Expiração

As tarefas e seus resultados permanecem disponíveis por aproximadamente 30
minutos contados desde a criação. As consultas não renovam esse período.

Depois da expiração, a consulta retorna HTTP `404`. A aplicação cliente deve
guardar o resultado necessário antes disso. A API não oferece histórico
permanente nesta etapa.

## Recomendações para produção

1. Defina timeout em todas as chamadas HTTP.
2. Armazene o `task_id` associado à operação que originou o CAPTCHA.
3. Aguarde entre as consultas de status.
4. Encerre o polling em `completed` ou `failed`.
5. Não registre imagens, tokens ou dados sensíveis desnecessariamente em logs.
6. Trate respostas HTTP e erros de processamento separadamente.
7. Não dependa da tarefa depois do TTL de 30 minutos.
