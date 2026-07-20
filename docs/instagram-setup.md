# Instagram自動連携 セットアップ手順

このリポジトリには、Instagramの最新投稿を毎日自動取得してサイトに表示する仕組みが組み込まれています。
以下の初回設定（手動・1回だけ）を行うと、以降は完全に自動で動作します。

## 全体の流れ

1. Instagramアカウントを「プロアカウント（ビジネス or クリエイター）」に切り替える
2. Meta for Developersでアプリを作成し、Instagram APIを追加する
3. アクセストークン（長期）とユーザーIDを取得する
4. GitHub Secretsに3つの値を登録する
5. GitHub Actionsが毎日自動実行され、投稿を取得・反映する

## 1. Instagramをプロアカウントに切り替える

Instagramアプリ → 設定 → アカウントの種類とツール → プロアカウントに切り替える（ビジネスまたはクリエイター）。

## 2. Meta for Developersでアプリを作成する

1. https://developers.facebook.com/ にアクセスし、ご自身のFacebookアカウントでログイン
2. 「マイアプリ」→「アプリを作成」
3. アプリタイプは「ビジネス」を選択
4. 作成後、アプリのダッシュボードで「製品を追加」から **Instagram** を追加
5. Instagram API の設定画面で、ご自身のInstagramプロアカウントを接続（Instagramでのログインを求められます）

## 3. アクセストークンとユーザーIDを取得する

1. Instagram API の設定画面にある「Generate token（トークンを生成）」から、接続したInstagramアカウント用のアクセストークンを生成
2. 生成されたトークンは「長期トークン」（有効期限 約60日、リフレッシュで延長可能）です
3. 同じ画面に表示される **Instagram User ID**（数字の羅列）も控えておく

## 4. GitHub Secretsに登録する

リポジトリの **Settings → Secrets and variables → Actions → New repository secret** から、以下の3つを登録してください。

| Secret名 | 値 |
|---|---|
| `IG_ACCESS_TOKEN` | 手順3で取得した長期アクセストークン |
| `IG_USER_ID` | 手順3で取得したInstagram User ID |
| `GH_PAT` | 下記の手順で発行するPersonal Access Token |

### GH_PATの発行方法
トークンを自動更新する際、GitHub Secrets自体を書き換える必要があるため、通常のワークフロー権限だけでは行えません。そのため専用のトークンを発行します。

1. GitHubの **Settings（自分のアカウント設定）→ Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
2. 対象リポジトリをこのリポジトリのみに限定
3. Permissions で **Secrets: Read and write** を付与
4. 発行されたトークンを `GH_PAT` としてリポジトリのSecretsに登録

## 5. 動作確認

1. リポジトリの **Actions** タブ → **Instagram Sync** ワークフローを選択
2. **Run workflow** で手動実行
3. 実行ログで投稿取得・画像保存が成功しているか確認
4. `data/instagram-posts.json` と `images/instagram/` フォルダにコミットが作成されていれば成功

以降は毎日自動実行され、`IG_ACCESS_TOKEN` も期限切れ前に自動更新されます。

## トラブルシューティング
- ワークフローが失敗する場合、Actionsのログに理由が表示されます（トークン切れ、権限不足など）
- `IG_ACCESS_TOKEN` の手動再発行が必要になった場合は、手順3をやり直してSecretsを上書きしてください
