# Bot共通 障害対応ランブック

## 障害パターンと対応

| 障害 | 検知方法 | 自動対応 | 人間エスカレーション |
|---|---|---|---|
| GitHub Actions実行失敗 | Discord通知（赤Embed） | なし | ワークフローログ確認→手動再実行 |
| Claude API 429 (Rate Limit) | ログ + Discord通知 | 指数バックオフ(3回) | 15分待って再実行 |
| Claude API 401 (Auth) | ログ + Discord通知 | なし | APIキー確認→GitHub Secrets更新 |
| Turso DB接続エラー | ログ | なし | Tursoダッシュボード確認 |
| X API BAN/凍結 | 投稿失敗ログ | kill_switch有効化 | アカウント状態確認 |
| Threads Token期限切れ | 投稿失敗(401) | threads-token-refresh.yml | 手動トークン再取得 |
| Discord Webhook無効 | 通知が来ない | なし | Webhook URL再生成→Secrets更新 |
| cron-job.org遅延/停止 | 予定時刻に実行なし | なし | cron-job.orgダッシュボード確認 |
| pip依存関係脆弱性 | pip-audit weekly | PR自動生成 | 修正版パッケージへのアップデート |
| SendGrid送信失敗 | SendLog.action=failed | なし | SendGridダッシュボード確認 |

## 復旧手順テンプレート
1. Discordの障害通知Embedから該当ワークフローのURLを開く
2. ログを確認し、エラーの種類を特定
3. 上記テーブルの「人間エスカレーション」列の手順を実行
4. 手動再実行: GitHub Actions → 該当ワークフロー → Run workflow
5. 成功を確認し、Discordに復旧報告

## APIキーローテーション手順
1. 各プロバイダーの管理画面で新キーを発行
2. GitHub Secretsを更新: Settings → Secrets → Actions → 該当キーを編集
3. ローカル.envを更新
4. ワークフローを手動実行して疎通確認
5. 旧キーを無効化
