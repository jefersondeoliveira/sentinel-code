# Spec: Notificações via Slack e E-mail ao Término do Pipeline

## Status
Fase 5 — [ ] Pendente

## Contexto
O pipeline SentinelCode pode demorar de 30 segundos a vários minutos dependendo
do tamanho do projeto e dos agentes ativos. Hoje o usuário precisa aguardar o
terminal ou monitorar o processo ativo. Em uso CI/CD ou em análises programadas,
é essencial notificar automaticamente a equipe quando a análise conclui e
quais issues críticos foram encontrados.

## Objetivo
Enviar notificação ao Slack e/ou e-mail ao término do pipeline com resumo dos
resultados (issues críticos, gaps, fixes aplicados, link para o relatório).

## Escopo

### Inclui
- Notificação Slack via Incoming Webhook (sem SDK, somente HTTP POST)
- Notificação e-mail via SMTP (suporta Gmail, Outlook, SMTP genérico)
- Configuração via variáveis de ambiente (`.env`)
- Flags opcionais no CLI: `--notify-slack`, `--notify-email`
- Mensagem com: projeto, nº de issues críticos, nº de fixes, link para o relatório HTML
- Falha silenciosa: notificação que falha não interrompe o pipeline

### Não inclui
- Microsoft Teams ou outras plataformas de chat
- Push notifications / webhooks customizados
- Notificações em tempo real durante o pipeline (somente ao término)
- Anexo do relatório PDF no e-mail (somente link para o arquivo local)

## Arquitetura

Novo nó opcional `notify_node` inserido após `render_report` no pipeline.
Ativado via flags do `build_full_pipeline()`.

```
render_report → [notify_node] → END
                    ↓
              slack_notifier.send()
              email_notifier.send()
```

## Mudanças no AgentState (`models/state.py`)
Nenhuma. O nó `notify_node` lê `final_report`, `issues` e `infra_gaps` do estado existente.

## Novos arquivos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `tools/notifications/slack_notifier.py` | `send_slack_notification(webhook_url, summary) -> bool` — HTTP POST para Incoming Webhook |
| `tools/notifications/email_notifier.py` | `send_email_notification(smtp_config, to, summary) -> bool` — SMTP via `smtplib` |
| `tools/notifications/summary_builder.py` | `build_notification_summary(state: AgentState) -> dict` — extrai métricas do estado |
| `tests/unit/test_notifications.py` | Testes com mock HTTP e SMTP (mínimo 10 testes) |

## Arquivos existentes a modificar

| Arquivo | O que muda |
|---------|-----------|
| `agents/orchestrator.py` | `build_full_pipeline()` aceita `with_slack: bool = False` e `with_email: bool = False`; adiciona `notify_node` após `render_report` |
| `main.py` | Flags `--notify-slack` e `--notify-email` |
| `config.py` | Novos campos: `slack_webhook_url: str | None`, `smtp_host: str | None`, `smtp_port: int`, `smtp_user: str | None`, `smtp_password: str | None`, `notify_email_to: str | None` |

## Fluxo de dados

```python
# tools/notifications/slack_notifier.py
def send_slack_notification(webhook_url: str, summary: dict) -> bool:
    payload = {
        "text": f"*SentinelCode — {summary['project']}*",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Projeto:* {summary['project']}\n"
                        f"*Issues críticos:* {summary['critical_issues']}\n"
                        f"*Fixes aplicados:* {summary['fixes_applied']}\n"
                        f"*Gaps de infra:* {summary['gaps']}\n"
                        f"*Relatório:* `{summary['report_path']}`"
                    )
                }
            }
        ]
    }
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.warning(f"Falha ao notificar Slack: {e}")
        return False

# .env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=sentinel@example.com
SMTP_PASSWORD=app-password-here
NOTIFY_EMAIL_TO=team@example.com
```

## Decisões técnicas

- **Slack Incoming Webhook**: sem dependência do SDK Slack; URL configurada no `.env`
- **SMTP**: `smtplib` da stdlib Python — sem biblioteca externa; suporte a TLS via `STARTTLS`
- **Gmail**: requer "App Password" (não a senha da conta) quando 2FA ativado
- **Falha silenciosa**: `try/except` em ambos os notificadores; log de warning, nunca raise
- **Conteúdo da notificação**: texto simples + métricas; não embute o HTML completo

## Critérios de aceitação

- [ ] `--notify-slack` com `SLACK_WEBHOOK_URL` configurado envia mensagem ao canal
- [ ] `--notify-email` com SMTP configurado envia e-mail ao destinatário
- [ ] Mensagem contém: projeto, issues críticos, fixes, path do relatório
- [ ] Webhook URL inválida não interrompe o pipeline (warning no log)
- [ ] Credenciais SMTP inválidas não interrompe o pipeline (warning no log)
- [ ] Pipeline sem flags de notificação não faz nenhuma requisição de notificação
- [ ] `pytest tests/unit/test_notifications.py` passa com HTTP e SMTP mockados

## Testes

```python
# tests/unit/test_notifications.py
# - test_slack_sends_post_with_correct_payload (mock requests)
# - test_slack_returns_true_on_200
# - test_slack_returns_false_on_error
# - test_slack_invalid_webhook_url_no_crash
# - test_email_sends_via_smtp (mock smtplib)
# - test_email_returns_true_on_success
# - test_email_smtp_error_no_crash
# - test_summary_builder_counts_critical_issues
# - test_summary_builder_counts_fixes
# - test_no_notifications_without_flags
```
