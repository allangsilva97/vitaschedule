# Segurança

## Arquitetura de segurança

Autenticação, autorização, validação, limite de tentativas e auditoria rodam **no servidor** (`api/`). O front só
exibe o que a API devolve; esconder botões é conveniência de UI, não controle de acesso. A sessão é um JWT em cookie
`HttpOnly; Secure; SameSite=Strict` (15 min deslizantes); mutações exigem o cabeçalho `X-Requested-With`; senhas usam
scrypt; horários duplos são barrados por índice único no banco. A API serve o `index.html` na mesma origem
(`connect-src 'self'`).

**Limites atuais:** o limitador de tentativas é em memória (vale por instância); 2FA ainda é só um campo; e-mails de
confirmação/lembrete e redefinição de senha **não são enviados** (apenas registrados); criptografia em repouso depende do
provedor do banco; não há tela nem endpoint para criar o primeiro usuário (com `SEED_DEMO=false` o banco começa sem
contas e o primeiro usuário precisa ser inserido direto nele). Os dados semeados com `SEED_DEMO=true` são fictícios e a
senha de demonstração é pública.

## O que o código já faz

- **Sem XSS:** todo texto vindo de formulário é escapado (`esc()`) ou inserido por `textContent`; não há
  `eval`, `document.write` nem handlers inline (`onclick=`); os eventos usam `data-action` com delegação.
  Revisadas as 133 interpolações de template do script: as que vão para HTML passam por `esc()` ou são
  números e constantes.
- **CSP rígida** (via `<meta>`): `default-src 'none'`; scripts liberados só por hash SHA-256 e estilos por hash
  mais as folhas do Font Awesome e do Google Fonts; sem `unsafe-inline` nem `unsafe-eval`;
  `connect-src 'self'` (só a própria API); `form-action 'none'`; `base-uri 'none'`; `object-src 'none'`.
  Nenhum script de terceiros (o Tailwind é compilado, não carregado de CDN).
- **SRI** no CSS do Font Awesome; `Referrer-Policy: no-referrer` via `<meta>`.
- **Anti-clickjacking de reserva:** se a página for aberta dentro de um `<iframe>`, ela não renderiza nada.
- **Login no servidor:** senhas com scrypt (salt por usuário), comparação em tempo constante, mesmo trabalho de
  hash quando a conta não existe, mensagem genérica de erro, limite de tentativas por IP e por conta, sessão em
  JWT num cookie `HttpOnly` de 15 min deslizantes e logout por inatividade.
- **Controle de acesso no servidor (RBAC):** cada rota confere o perfil; o médico vê só os próprios pacientes;
  o paciente cancela só as próprias consultas; o último administrador não pode ser removido. O front só esconde
  botões por conveniência.
- **IP do cliente nos limitadores:** com `TRUSTED_PROXY_HOPS=N` vale a N-ésima entrada de `X-Forwarded-For`
  contada da direita (a que o proxy de confiança acrescentou). Nunca use `--forwarded-allow-ips='*'` no uvicorn:
  ele passa a aceitar a primeira entrada, que o cliente forja, e os limitadores deixam de proteger.
- **Validações:** CPF com dígitos verificadores, datas, horários e convênios em lista fixa, anti-duplicidade
  de horário, protocolo aleatório (`crypto.getRandomValues`).
- **LGPD (o que dá para fazer sem servidor):** CPF e nome mascarados, consentimento registrado, consulta
  pública exige protocolo + CPF, trilha de auditoria sem dados digitados pelo usuário.

## O que NÃO está resolvido

| Ponto | Por quê |
| --- | --- |
| Limite de tentativas entre várias instâncias | O limitador vive na memória de cada instância; com mais de uma, o limite real é maior. Use um armazenamento compartilhado (Redis). |
| Bloqueio de conta por terceiros | O limite por conta (`id:`) trava o login de qualquer e-mail após 5 erros seguidos, mesmo vindo de outra pessoa. |
| Criptografia em repouso | Depende do provedor do Postgres. |
| Auditoria imutável | A trilha fica numa tabela comum do banco, que um administrador do banco pode alterar. |
| 2FA | A coluna "2FA" é só visual. |
| E-mails | Confirmação, lembrete e redefinição de senha só são registrados, não enviados. |
| Google Fonts | A fonte é carregada do Google, que recebe o IP do visitante. Para LGPD estrita, hospede a Inter localmente. |
| Cabeçalhos HTTP no GitHub Pages | `frame-ancestors`, `X-Frame-Options`, `nosniff` e HSTS só funcionam como cabeçalho (veja `_headers`; a API já os envia). |

## Checklist antes de usar com dados reais

1. Definir `SEED_DEMO=false`, remover as contas e a senha de demonstração e criar usuários de verdade.
2. Definir `APP_ENV=production` e um `SECRET_KEY` aleatório (o app não sobe sem ele).
3. Definir `TRUSTED_PROXY_HOPS` conforme os proxies na frente do app e conferir nos logs o IP gravado.
4. Ativar 2FA de verdade e um limitador compartilhado se houver mais de uma instância.
5. Criptografar o banco, fazer backup e manter uma trilha de auditoria imutável.
6. Servir só por HTTPS e enviar os cabeçalhos do `_headers` se o front ficar em outro host.
7. Hospedar fontes e ícones localmente e revisar a base legal e o consentimento (LGPD).

## Dependências

O build usa Tailwind 3.4.17, fixado no `package-lock.json`, com integridade conferida. Instale com
`npm ci --ignore-scripts`. O `npm audit` não encontrou vulnerabilidades em 20/11/2026. O `index.html` publicado
não carrega nenhum pacote npm.

A API usa versões fixas em `api/requirements.txt`; o `pip-audit` não encontrou vulnerabilidades conhecidas nelas em
20/11/2026. Rode `pip-audit` de novo antes de cada deploy.

## Como reportar uma vulnerabilidade

Use a aba **Security** do repositório no GitHub (*Report a vulnerability*). Se ela não estiver disponível,
abra uma issue pedindo contato, sem colocar detalhes da falha em público.
