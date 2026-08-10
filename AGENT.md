# AGENTS.md

Este arquivo define as regras obrigatórias que qualquer agente automatizado deve seguir ao trabalhar neste projeto.

As instruções aqui descritas têm prioridade sobre decisões autônomas do agente. Caso uma tarefa entre em conflito com estas regras, o agente deve **interromper a operação conflitante**, preservar o estado atual do projeto e informar a limitação.

---

## 1. Documentação

Toda alteração realizada no projeto deve ser devidamente documentada na pasta `DOCS/`.

Sempre que houver alterações em:

* funcionalidades;
* arquitetura;
* configurações;
* integrações;
* APIs;
* modelos;
* serviços;
* fluxos;
* regras de negócio;
* dependências;
* comportamentos do sistema;

o agente deve verificar se a documentação correspondente também precisa ser atualizada.

### Regras obrigatórias

O agente deve:

* Atualizar a documentação existente quando ela for afetada pela alteração.
* Criar nova documentação quando a funcionalidade ainda não estiver documentada.
* Manter a documentação sincronizada com o comportamento atual do código.
* Remover ou corrigir documentação obsoleta quando necessário.
* Documentar decisões arquiteturais relevantes.
* Não considerar uma tarefa concluída enquanto a documentação necessária estiver desatualizada.

A documentação deve refletir **o estado final do projeto**, e não apenas descrever as alterações realizadas.

---

## 2. Controle de acesso do Agent

O agente **não possui permissão global de escrita no projeto**.

Por padrão, qualquer módulo, app, arquivo ou diretório deve ser considerado:

> **READ-ONLY — somente leitura**

A permissão de escrita somente existe quando estiver explicitamente definida neste arquivo ou concedida diretamente pelo usuário durante a tarefa atual.

O agente pode analisar código em módulos somente leitura para compreender dependências, arquitetura e comportamento do sistema, mas **não pode modificá-los**.

---

## 3. Apps Django e permissões

### Apps com acesso controlado

| App Django | Permissão            | Restrições                                                                                                                                          |
| ---------- | -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `captchas` | ⚠️ Leitura e análise | Pode analisar, estudar, propor alterações e executar tarefas que não modifiquem código. Alterações de código exigem liberação explícita do usuário. |

### Regra para apps não listados

Qualquer app Django que não esteja explicitamente listado como editável deve ser considerado:

> 🔒 **READ-ONLY**

Isso inclui código, migrations, testes, configurações e arquivos relacionados ao app.

---

## 4. Liberação para edição

A autorização para modificar um módulo deve ser **explícita**.

Exemplos válidos de autorização:

* "Pode modificar o app `captchas`."
* "Está liberado para implementar isso em `captchas`."
* "Pode alterar esses arquivos."
* "Pode fazer as modificações necessárias nesse módulo."

A simples solicitação para:

* analisar;
* investigar;
* estudar;
* explicar;
* revisar;
* pesquisar;
* sugerir;
* planejar;

**não concede permissão de escrita**.

A autorização concedida para um módulo não deve ser automaticamente estendida para outros módulos.

---

## 5. Regras de modificação

O agente deve obedecer estritamente às seguintes regras:

* Não modificar módulos sem autorização.
* Não criar novos apps Django sem autorização explícita.
* Não excluir apps Django sem autorização explícita.
* Não mover código entre apps sem autorização.
* Não renomear módulos ou apps sem autorização.
* Não refatorar módulos bloqueados.
* Não alterar migrations pertencentes a apps bloqueados.
* Não alterar testes de módulos bloqueados apenas para fazer uma implementação passar.
* Não alterar configurações globais como forma de contornar uma restrição de módulo.
* Não modificar código fora do escopo solicitado apenas por conveniência.
* Não expandir autonomamente o escopo de uma tarefa.

Caso uma implementação dependa de uma alteração em um módulo bloqueado, o agente deve:

1. Não realizar a alteração.
2. Identificar claramente a dependência.
3. Explicar qual modificação seria necessária.
4. Solicitar ou aguardar autorização explícita antes de executá-la.

Nunca contorne uma restrição de acesso por meio de outro arquivo ou módulo.

---

## 6. Alterações mínimas

Sempre prefira a menor alteração capaz de resolver corretamente o problema.

Evite:

* refatorações não solicitadas;
* mudanças puramente estéticas fora do escopo;
* renomeações desnecessárias;
* alterações arquiteturais sem necessidade;
* substituição de bibliotecas sem justificativa;
* mudanças em APIs públicas sem necessidade.

Preserve, sempre que possível:

* compatibilidade;
* comportamento existente;
* estrutura do projeto;
* convenções já utilizadas;
* APIs públicas existentes.

---

## 7. Segurança e informações sensíveis

Nunca envie informações sensíveis para o GitHub ou qualquer outro repositório remoto.

Considere como informação sensível, entre outras:

* senhas;
* tokens de autenticação;
* API keys;
* secrets;
* credenciais de banco de dados;
* chaves privadas;
* certificados privados;
* cookies;
* sessões;
* arquivos `.env`;
* credenciais de serviços externos;
* connection strings contendo credenciais;
* dados pessoais;
* informações internas que não devam ser públicas.

Informações sensíveis devem permanecer no ambiente local ou ser fornecidas através de mecanismos seguros, como variáveis de ambiente.

Nunca:

* escreva secrets diretamente no código;
* inclua credenciais reais em documentação;
* inclua credenciais reais em testes;
* inclua credenciais reais em exemplos;
* envie secrets em commits;
* exponha valores sensíveis em logs;
* copie valores reais para arquivos de exemplo.

---

## 8. Arquivos de configuração

Configurações sensíveis devem utilizar variáveis de ambiente sempre que possível.

Exemplo:

```python
import os

API_KEY = os.environ["API_KEY"]
```

Evite:

```python
API_KEY = "chave-real-do-servico"
```

Quando for necessário fornecer um arquivo de configuração de exemplo, utilize valores vazios ou placeholders.

Exemplo:

```env
DATABASE_URL=
SECRET_KEY=
API_KEY=
```

Ou:

```env
DATABASE_URL=<database-url>
SECRET_KEY=<secret-key>
API_KEY=<api-key>
```

Nunca utilize valores reais nesses arquivos.

---

## 9. `.gitignore`

O arquivo `.gitignore` deve ser mantido atualizado para impedir o versionamento acidental de arquivos:

* sensíveis;
* locais;
* temporários;
* gerados automaticamente;
* específicos do ambiente de desenvolvimento.

Exemplos comuns:

```gitignore
.env
.env.*
!.env.example

*.pem
*.key

*.log

__pycache__/
*.py[cod]

.venv/
venv/

.idea/
.vscode/
```

Antes de adicionar um novo tipo de arquivo ao projeto, verifique se ele pode conter dados sensíveis ou específicos do ambiente local.

Arquivos contendo secrets devem permanecer ignorados pelo Git.

---

## 10. Arquivos `.env`

Arquivos reais de ambiente não devem ser versionados.

Exemplos:

```text
.env
.env.local
.env.production
.env.development
.env.test
```

Quando necessário, mantenha apenas um arquivo seguro de referência:

```text
.env.example
```

O `.env.example` deve conter somente:

* nomes das variáveis;
* valores vazios;
* placeholders;
* valores públicos e comprovadamente não sensíveis.

---

## 11. Git e commits

Antes de preparar qualquer alteração para commit ou envio ao GitHub, o agente deve revisar o conjunto completo de mudanças.

Deve verificar:

1. Quais arquivos foram modificados.
2. Se todas as alterações pertencem ao escopo solicitado.
3. Se algum arquivo sensível foi adicionado.
4. Se existem senhas, tokens, secrets ou credenciais no diff.
5. Se o `.gitignore` protege arquivos sensíveis adequadamente.
6. Se arquivos `.env` reais foram adicionados acidentalmente.
7. Se a documentação correspondente em `DOCS/` foi atualizada.
8. Se nenhuma proteção de segurança foi removida.
9. Se nenhum módulo sem autorização foi modificado.

O agente nunca deve executar ações equivalentes a:

```bash
git add .
```

de forma cega sem antes verificar quais arquivos serão adicionados.

Antes de adicionar arquivos, prefira inspecionar:

```bash
git status
git diff
git diff --staged
```

---

## 12. Proteções existentes

Não remova ou desative mecanismos de segurança apenas para facilitar:

* desenvolvimento;
* testes;
* debugging;
* integração;
* execução local;
* automações.

Isso inclui, entre outros:

* autenticação;
* autorização;
* validações;
* permissões;
* proteção CSRF;
* validação de origem;
* rate limiting;
* verificações de acesso;
* tratamento seguro de secrets.

Caso uma proteção esteja impedindo uma tarefa, investigue a causa em vez de simplesmente removê-la.

---

## 13. Dependências

Não adicione, remova ou substitua dependências sem necessidade técnica clara.

Antes de adicionar uma nova dependência, verifique se:

* o projeto já possui uma solução equivalente;
* a biblioteca é realmente necessária;
* a funcionalidade não pode ser implementada usando os recursos atuais;
* a dependência é adequada ao projeto.

Mudanças relevantes nas dependências também devem ser documentadas em `DOCS/`.

---

## 14. Em caso de dúvida

Se houver dúvida sobre:

* permissão para modificar determinado arquivo;
* possibilidade de versionar determinada informação;
* presença de dados sensíveis;
* impacto de uma alteração fora do escopo;
* necessidade de modificar um módulo bloqueado;

o agente deve adotar a opção mais conservadora.

Isso significa:

> **Não modificar, não expor e não versionar até que exista autorização ou certeza suficiente.**

---

## 15. Ordem de prioridade

Ao executar qualquer tarefa, siga esta ordem de prioridade:

1. **Segurança e proteção de informações sensíveis.**
2. **Restrições de acesso aos módulos.**
3. **Preservação do comportamento existente.**
4. **Escopo definido pelo usuário.**
5. **Qualidade e correção da implementação.**
6. **Documentação atualizada em `DOCS/`.**
7. **Conveniência de desenvolvimento.**

Nenhuma conveniência técnica justifica violar uma regra de segurança ou uma restrição de acesso definida neste arquivo.
