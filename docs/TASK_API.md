# API de tarefas de CAPTCHA

Esta primeira etapa implementa criação e consulta de tarefas temporárias, com
processamento assíncrono pelo Celery e integração com o CaptchaAI. Não há
persistência dessas tarefas no banco de dados.

Todas as requisições exigem uma chave ativa no cabeçalho `X-API-Key` (ou
`Authorization: Bearer <chave>`). A chave é validada pelo app
`authentication`, incluindo sua data de expiração e seu limite de threads.

## Componentes

```text
POST /api/v1/tasks/
        ↓
CaptchaTaskRepository → Redis/cache (TTL de 30 minutos)
        ↓
Celery → solver → CaptchaAIClient → in.php / res.php
        ↓
Redis/cache ← COMPLETED ou FAILED
        ↓
GET /api/v1/tasks/{task_id}/
```

O repositório centraliza as transições internas `PENDING`, `PROCESSING`,
`COMPLETED` e `FAILED`. A API apresenta `PENDING` ao cliente como
`PROCESSING`, para que o estado interno de espera do worker não seja exposto.
Cada atualização reutiliza o instante de expiração original, evitando
que o TTL seja renovado durante o processamento.

Antes de criar uma tarefa, uma thread é reservada atomicamente para a chave. Se
`max_threads` já estiver ocupado, a API responde `429` e não cria nem enfileira
a tarefa. A reserva é liberada quando o processamento termina ou quando ocorre
falha ao publicar no Celery.

## Tipos disponíveis

São aceitos todos os módulos descritos no guia CaptchaAI do projeto:

| `captcha_type` | Campos em `data` |
| --- | --- |
| `normal` | `body` (Base64), `filename?`, `content_type?`, `regsense?`, `numeric?` |
| `grid` | `body` (Base64), `grid_size`, `img_type`, `instructions` |
| `recaptcha_v2` | `googlekey`, `pageurl` |
| `recaptcha_v2_invisible` | `googlekey`, `pageurl` |
| `recaptcha_v2_callback` | `googlekey`, `pageurl` |
| `recaptcha_v2_enterprise` | `googlekey`, `pageurl`, `action?` |
| `recaptcha_v3` | `googlekey`, `pageurl`, `action` |
| `recaptcha_v3_enterprise` | `googlekey`, `pageurl`, `action` |
| `geetest_v3` | `gt`, `challenge`, `pageurl`, `api_server?` |
| `turnstile` | `sitekey`, `pageurl` |
| `cloudflare_challenge` | `pageurl`, `proxy?`, `proxytype?`, `user_agent?` |
| `bls` | `instructions`, `images` (lista de 9 data URIs Base64) |
| `captchafox` | `sitekey`, `pageurl`, `proxy?`, `proxytype?` |
| `friendly_captcha` | `sitekey`, `pageurl` |
| `lemin` | `captcha_id`, `pageurl`, `div_id?` |

Novos tipos podem ser adicionados implementando o contrato de solver e
registrando-o em `services/captchaai/solvers.py`. As views e o repositório não
dependem de um tipo específico.

O tipo `recaptcha_v2_callback` usa o mesmo `method=userrecaptcha` do v2 normal.
O nome representa a forma como a aplicação consumirá o token; não existe um
método de provider separado para callback.

### Imagens

Para manter a mensagem enviada ao Celery serializável, `normal` e `grid`
recebem a imagem como Base64 no campo `body`. Também é aceita uma data URI. O
worker valida o formato e o limite documentado de 100 bytes a 100 KB, converte
o conteúdo e cria o upload multipart para o CaptchaAI.

```json
{
  "captcha_type": "normal",
  "data": {
    "body": "<imagem-em-base64>",
    "content_type": "image/png"
  }
}
```

JPG/JPEG, PNG e GIF são aceitos. No BLS, `images` deve possuir exatamente nove
data URIs, preservadas como os campos `image_base64_1` até `image_base64_9`.

## Criar uma tarefa

```http
POST /api/v1/tasks/
Content-Type: application/json

{
  "captcha_type": "recaptcha_v2",
  "data": {
    "googlekey": "<site-key>",
    "pageurl": "https://example.test/captcha"
  }
}
```

Resposta `202 Accepted`:

```json
{
  "task_id": "4dd69e6c-781b-49ba-b59d-f3201507121f",
  "status": "processing"
}
```

## Consultar uma tarefa

```http
GET /api/v1/tasks/4dd69e6c-781b-49ba-b59d-f3201507121f/
```

O resultado concluído possui a forma:

```json
{
  "task_id": "4dd69e6c-781b-49ba-b59d-f3201507121f",
  "status": "completed",
  "result": {"solution": "..."}
}
```

Para `grid` e `bls`, `result.solution` é uma lista de posições. Para
`geetest_v3`, é um objeto com `challenge`, `validate` e `seccode`. Os demais
módulos retornam texto/token e, quando fornecido pelo CaptchaAI, `user_agent` é
preservado no resultado.

Falhas usam `status=failed` e um objeto `error` com `code` e `message`. Uma
tarefa ausente ou expirada retorna HTTP 404.

## Configuração

```env
REDIS_URL=redis://localhost:6379/0
CACHE_URL=redis://localhost:6379/2
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
CAPTCHA_TASK_TTL=1800
CAPTCHAAI_API_KEY=
CAPTCHAAI_BASE_URL=https://ocr.captchaai.com
CAPTCHAAI_REQUEST_TIMEOUT=30
CAPTCHAAI_POLL_INTERVAL=5
CAPTCHAAI_TASK_TIMEOUT=120
```

Inicie um worker com:

```bash
celery -A conf worker --loglevel=INFO
```

Os testes substituem o cache por memória e simulam o cliente CaptchaAI; eles
não acessam o serviço externo.
