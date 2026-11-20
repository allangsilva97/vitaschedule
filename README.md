# VitaSchedule

Sistema de agendamento e gestão de pacientes para clínicas: front em um único `index.html` + API FastAPI
(`api/`) com Postgres e migrações Alembic. Login, perfis, regras e auditoria são validados **no servidor**.

> **Aviso:** os dados de demonstração são fictícios. Antes de usar com pacientes reais, leia o
> checklist em [SECURITY.md](SECURITY.md).

## O que tem

- **Paciente:** agenda consultas, cancela as próprias e acompanha o status.
- **Recepção:** agenda presencialmente, atualiza status e vê a agenda de todos os profissionais.
- **Médico(a):** vê só os próprios pacientes e prontuários e bloqueia a própria agenda.
- **Administrador:** gerencia usuários, vê a auditoria e o status de conformidade.
- **Consulta pública de status:** exige protocolo **e** CPF, e devolve apenas dados mínimos.
- Tema claro/escuro e interface responsiva.

## API, banco e deploy

```bash
cd api
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # Linux/Mac: .venv/bin/pip
.venv/Scripts/alembic upgrade head                                          # cria as tabelas (SQLite local por padrão)
SEED_DEMO=true .venv/Scripts/uvicorn app.main:app --reload                  # http://localhost:8000
.venv/Scripts/python -m pytest                                              # testes
```

Variáveis: `DATABASE_URL` (Postgres em produção), `SECRET_KEY` (obrigatória com `APP_ENV=production`),
`SEED_DEMO` (cria contas/dados fictícios se o banco estiver vazio), `DEMO_PASSWORD`,
`TRUSTED_PROXY_HOPS` (quantos proxies de confiança ficam na frente; padrão 0, usado só para o IP dos limitadores).
Nova migração: `alembic revision --autogenerate -m "descrição"`.

Deploy: `render.yaml` (Render > New > Blueprint). A API serve o `index.html` na mesma origem, então o cookie
de sessão é `HttpOnly; Secure; SameSite=Strict` e não há CORS.

## Contas de demonstração

Na tela de login (botão **Entrar**) há um seletor de perfil que preenche o e-mail da conta de demonstração e
mostra a senha de demonstração (`DEMO_PASSWORD`, padrão `Vita#Demo2026`). As contas são:

| Perfil | E-mail |
| --- | --- |
| Paciente | `paciente@vitamed.com` |
| Recepção | `recepcao@vitamed.com` |
| Médica | `mariana.souza@vitamed.com` |
| Administrador | `admin@vitamed.com` |

A caixa de demonstração e as contas só existem com `SEED_DEMO=true` no servidor. Para desligar, defina `SEED_DEMO=false`.

## Estrutura

```
index.html      front (HTML + CSS compilado + JavaScript)
api/            FastAPI + SQLAlchemy + Alembic (migrações em api/alembic)
render.yaml     deploy no Render (web + Postgres)
build/          ferramenta de build (Tailwind + hashes da CSP)
_headers        cabeçalhos de segurança para Netlify / Cloudflare Pages
SECURITY.md     modelo de segurança, limites e checklist para produção
```

## Desenvolvimento

O CSS do Tailwind é compilado e embutido no `index.html`, e a Content-Security-Policy libera o script e o
CSS **por hash** (sem `unsafe-inline`). Por isso, depois de editar o `index.html` (classes do Tailwind ou o
`<script>`), rode o build para recompilar o CSS e atualizar os hashes; sem isso o navegador bloqueia o que mudou.

Rode os comandos abaixo **na raiz do projeto** (a pasta que tem o `index.html`). É preciso ter o
[Node.js](https://nodejs.org) instalado.

```bash
npm run setup   # só na primeira vez (instala o Tailwind 3.4.17 fixado no package-lock.json)
npm run build   # depois de cada edição no index.html
```

Não edite à mão o bloco `<style>` nem os hashes da CSP: eles são regenerados a cada build.

## Hospedagem

- **GitHub Pages:** funciona, mas não aceita cabeçalhos HTTP personalizados. O código anti-iframe do
  próprio `index.html` cobre o clickjacking nesse caso.
- **Netlify / Cloudflare Pages:** o arquivo `_headers` já aplica `frame-ancestors`, `nosniff`, HSTS e outros.
- Sempre sirva por **HTTPS**.
