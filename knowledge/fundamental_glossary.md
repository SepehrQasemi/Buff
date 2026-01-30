# Fundamental Risk Glossary

## Domains
- Macro: Economic policy, inflation, and rate-sensitive signals.
- Onchain: Blockchain-based network stress indicators and supply dynamics.
- News: Event-risk windows and shock indicators derived from headlines.

## States
- macro_risk_state: low / medium / high / unknown
- onchain_stress_level: normal / elevated / extreme / unknown
- news_risk_flag: true / false / unknown
- final_risk_state: green / yellow / red

## Evidence
Evidence captures rule evaluations (matched or not), inputs used, severity, and a reason string
for auditability. The system only emits permission and risk states; it never outputs trade
signals or predictions.
