import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, date
import jaconv
import io

# ==========================================
# 1. データベース接続設定
# ==========================================
try:
    url: str = st.secrets["SUPABASE_URL"]
    key: str = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("設定ファイル（secrets.toml）が正しく読み込めません。")
    st.stop()

# ==========================================
# 2. ページ設定とセッション状態の初期化
# ==========================================
st.set_page_config(page_title="会員・会費管理システム", page_icon="⚽", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_role' not in st.session_state:
    st.session_state.user_role = None
if 'assigned_category' not in st.session_state:
    st.session_state.assigned_category = None
if 'current_view' not in st.session_state:
    st.session_state.current_view = 'list' # 'list', 'detail', 'new'
if 'selected_member_id' not in st.session_state:
    st.session_state.selected_member_id = None
if 'show_billing_data' not in st.session_state:
    st.session_state.show_billing_data = False
    
# 🌟 手動マッチング（学習）用のポケット
if 'unmatched_records' not in st.session_state:
    st.session_state.unmatched_records = []
if 'last_imported_month' not in st.session_state:
    st.session_state.last_imported_month = None

# Supabaseの認証チケットを保持するためのポケット
if 'access_token' not in st.session_state:
    st.session_state.access_token = None
if 'refresh_token' not in st.session_state:
    st.session_state.refresh_token = None

# ポケットにチケットがあれば、Supabaseに提示して「ログイン済み」であることを証明する
if st.session_state.access_token and st.session_state.refresh_token:
    try:
        supabase.auth.set_session(st.session_state.access_token, st.session_state.refresh_token)
    except Exception as e:
        pass # チケットの期限切れ等の場合は無視

# ==========================================
# 3. 共通ロジック
# ==========================================
def calculate_age_and_category(dob, target_date=None):
    if not dob:
        return None, None
    if target_date is None:
        target_date = datetime.now().date()
        
    target_fy = target_date.year if target_date.month >= 4 else target_date.year - 1
    
    if dob.month > 4 or (dob.month == 4 and dob.day >= 2):
        school_year_born = dob.year
    else:
        school_year_born = dob.year - 1
        
    age = target_fy - school_year_born
    
    if age <= 6: cat = "U-6"
    elif age == 7: cat = "U-7"
    elif age == 8: cat = "U-8"
    elif age == 9: cat = "U-9"
    elif age == 10: cat = "U-10"
    elif age == 11: cat = "U-11"
    elif age == 12: cat = "U-12"
    elif age == 13: cat = "U-13"
    elif age == 14: cat = "U-14"
    elif age == 15: cat = "U-15"
    elif 16 <= age <= 18: cat = "U-18"
    else: cat = "トップ"
    return age, cat

def get_auto_fee(category):
    if category in ["U-6", "U-7", "U-8", "U-9"]: return 7865
    elif category in ["U-10", "U-11", "U-12"]: return 12100
    elif category in ["U-13", "U-14", "U-15", "U-18"]: return 16940
    else: return 0

def clean_kana(text):
    if not text: return ""
    kata = jaconv.hira2kata(str(text))
    half = jaconv.z2h(kata, kana=True, digit=True, ascii=True).upper()
    return half

def pad_str(text, length):
    return clean_kana(text).ljust(length, ' ')[:length]

def pad_num(num, length):
    return str(num).zfill(length)[:length]

# ==========================================
# 4. ログイン画面
# ==========================================
if not st.session_state.logged_in:
    st.title("⚽ ブリオベッカ浦安 ログイン")
    with st.container():
        st.write("システムを利用するにはログインしてください。")
        login_id = st.text_input("ログインID (メールアドレス)")
        password = st.text_input("パスワード", type="password")
        
        if st.button("ログイン", type="primary"):
            try:
                auth_response = supabase.auth.sign_in_with_password({"email": login_id, "password": password})
                st.session_state.access_token = auth_response.session.access_token
                st.session_state.refresh_token = auth_response.session.refresh_token
                
                response = supabase.table("staff_users").select("*").eq("login_id", login_id).execute()
                users = response.data
                
                if len(users) > 0:
                    user = users[0]
                    st.session_state.logged_in = True
                    st.session_state.user_role = user.get('role', 'coach')
                    st.session_state.assigned_category = user.get('assigned_category', '')
                    st.cache_data.clear()
                    st.success("🔒 セキュアログインに成功しました！")
                    st.rerun()
                else:
                    st.error("認証には成功しましたが、スタッフ権限（役職）が設定されていません。")
            except Exception as e:
                st.error("メールアドレスまたはパスワードが間違っています。")
    st.stop()

# ==========================================
# 5. ヘッダー
# ==========================================
col_title, col_logout = st.columns([8, 2])
with col_title:
    st.title("⚽ ブリオベッカ浦安 会員・会費管理")
with col_logout:
    role_text = "管理者" if st.session_state.user_role == 'admin' else f"コーチ ({st.session_state.assigned_category})"
    st.write(f"👤 {role_text}")
    if st.button("ログアウト"):
        try:
            supabase.auth.sign_out()
        except:
            pass
        st.session_state.logged_in = False
        st.session_state.access_token = None
        st.session_state.refresh_token = None
        st.session_state.current_view = 'list'
        st.session_state.show_billing_data = False
        st.session_state.unmatched_records = []
        st.rerun()

st.divider()

# ==========================================
# データ取得
# ==========================================
@st.cache_data(ttl=10)
def get_all_data():
    p_res = supabase.table("parents").select("*").execute()
    a_res = supabase.table("bank_accounts").select("*").execute()
    m_res = supabase.table("members").select("*").order("created_at", desc=True).execute()
    b_res = supabase.table("billings").select("*").execute()
    return p_res.data, a_res.data, m_res.data, b_res.data

parents_data, accounts_data, members_data, billings_data = get_all_data()

# ログイン権限によるタブの制御
if st.session_state.user_role == 'admin':
    tab_options = ["📋 選手名簿管理", "💰 請求データ生成 (全銀出力)", "💳 引落結果の取込 (消込)", "⚙️ システム管理 (入出力・年度更新)", "📊 ダッシュボード", "⚙️ アカウント設定"]
else:
    tab_options = ["📋 選手名簿管理", "⚙️ アカウント設定"]

if 'active_tab' not in st.session_state or st.session_state.active_tab not in tab_options:
    st.session_state.active_tab = "📋 選手名簿管理"

selected_tab = st.radio("メニュー", tab_options, horizontal=True, label_visibility="collapsed", key="active_tab")
st.markdown("---")

# ==========================================
# 【TAB 1】選手名簿管理 (List / Detail)
# ==========================================
if selected_tab == "📋 選手名簿管理":
    if st.session_state.current_view == 'list':
        st.header("📋 選手名簿一覧")
        
        col_filter, col_btn = st.columns([3, 1])
        if st.session_state.user_role == 'coach':
            selected_category = st.session_state.assigned_category
            with col_filter:
                st.info(f"あなたの担当カテゴリ（{selected_category}）のみ表示しています。")
        else:
            with col_filter:
                cat_options = ["すべて", "U-6", "U-7", "U-8", "U-9", "U-10", "U-11", "U-12", "U-13", "U-14", "U-15", "U-18", "トップ"]
                selected_category = st.selectbox("カテゴリで絞り込み", options=cat_options)
        
        with col_btn:
            st.write("")
            if st.button("➕ 新規選手を登録", type="primary", use_container_width=True):
                st.session_state.current_view = 'new'
                st.rerun()

        if members_data:
            df_m = pd.DataFrame(members_data)
            if selected_category != "すべて":
                df_m = df_m[df_m['category'] == selected_category]
                
            if not df_m.empty:
                df_m['選手名'] = df_m['last_name'] + ' ' + df_m['first_name']
                st.write(f"該当件数: {len(df_m)}名")
                
                header_cols = st.columns([1.2, 2.0, 1.2, 1.2, 1.8, 1.8, 1.2])
                header_cols[0].markdown("**カテゴリー**")
                header_cols[1].markdown("**選手名**")
                header_cols[2].markdown("**ｽﾃｰﾀｽ**")
                header_cols[3].markdown("**月会費**")
                header_cols[4].markdown("**入会日**")
                header_cols[5].markdown("**退会日**")
                header_cols[6].markdown("**詳細**")
                st.divider()
                
                for idx, row in df_m.iterrows():
                    row_cols = st.columns([1.2, 2.0, 1.2, 1.2, 1.8, 1.8, 1.2])
                    row_cols[0].write(row['category'])
                    row_cols[1].write(row['選手名'])
                    row_cols[2].write(row['status'])
                    row_cols[3].write(f"¥{int(row['base_monthly_fee']):,}") 
                    
                    join_str = row['join_date'] if pd.notna(row['join_date']) and row['join_date'] else "-"
                    leave_str = row['leave_date'] if pd.notna(row['leave_date']) and row['leave_date'] else "-"
                    row_cols[4].write(join_str)
                    row_cols[5].write(leave_str)
                    
                    if row_cols[6].button("詳細 📝", key=f"btn_detail_{row['id']}", use_container_width=True):
                        st.session_state.selected_member_id = row['id']
                        st.session_state.current_view = 'detail'
                        st.rerun()
                    st.write("") 
            else:
                st.info("該当する選手がいません。")
        else:
            st.info("登録されている選手がいません。")

    elif st.session_state.current_view in ['detail', 'new']:
        is_new = (st.session_state.current_view == 'new')
        header_text = "➕ 新規選手の登録" if is_new else "✏️ 選手情報の閲覧・編集"
        st.header(header_text)
        
        if st.button("◀ 一覧へ戻る"):
            st.session_state.current_view = 'list'
            st.session_state.selected_member_id = None
            st.rerun()
            
        target_member = {}
        target_parent = {}
        target_account = {}
        
        if not is_new and st.session_state.selected_member_id:
            target_member = next((m for m in members_data if m['id'] == st.session_state.selected_member_id), {})
            target_parent = next((p for p in parents_data if p['id'] == target_member.get('parent_id')), {})
            target_account = next((a for a in accounts_data if a['id'] == target_member.get('account_id')), {})

        with st.container():
            st.subheader("🏃 選手情報")
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                m_last = st.text_input("姓 ※必須", value=target_member.get('last_name', ''))
                m_first = st.text_input("名 ※必須", value=target_member.get('first_name', ''))
            with col_m2:
                default_dob = datetime.strptime(target_member['birthdate'], '%Y-%m-%d').date() if target_member.get('birthdate') else None
                m_dob = st.date_input("生年月日", value=default_dob, min_value=date(1990, 1, 1), max_value=date.today())
                calc_age, calc_cat = calculate_age_and_category(m_dob)
                
            col_m3, col_m4, col_m5 = st.columns(3)
            with col_m3:
                m_status = st.selectbox("ステータス", ["在籍", "休会", "退会", "特待"], index=["在籍", "休会", "退会", "特待"].index(target_member.get('status', '在籍')) if target_member.get('status') else 0)
            with col_m4:
                default_join = datetime.strptime(target_member['join_date'], '%Y-%m-%d').date() if target_member.get('join_date') else date.today()
                m_join = st.date_input("入会日 (請求開始月の判定用)", value=default_join)
            with col_m5:
                default_leave = datetime.strptime(target_member['leave_date'], '%Y-%m-%d').date() if target_member.get('leave_date') else None
                m_leave = st.date_input("休会・退会日 (請求停止月の判定用)", value=default_leave)
                
            if m_leave and m_status == "在籍":
                st.warning("⚠️ 退会日が入力されているため、保存時にステータスは自動的に「退会」に更新されます。")
                
            st.markdown("---")
            st.markdown("**💰 月会費の設定**")
            auto_fee = get_auto_fee(calc_cat) if calc_cat else 12000
            current_db_fee = target_member.get('base_monthly_fee', auto_fee)
            is_custom = target_member.get('is_custom_fee', False)
            
            use_custom_fee = st.checkbox("手動で月会費を設定する（兄弟割・特待生など、規定料金以外にする場合のみチェック）", value=is_custom)
            
            if use_custom_fee:
                st.warning("⚠️ 手動設定がオンになっています。4月の年度更新時にも金額は自動変更されません。")
                m_fee = st.number_input("特別月会費 (円)", value=int(current_db_fee), step=100)
            else:
                st.info(f"💡 生年月日と現在のカテゴリ（{calc_cat}）に基づき、規定の月会費 ¥{int(auto_fee):,}が自動適用されています。")
                m_fee = current_db_fee if not is_new else auto_fee
                
            st.divider()

            st.subheader("👥 保護者情報")
            parent_options = {}
            for p in parents_data:
                label = p['name']
                if p.get('name_2'): label += f" / {p['name_2']}"
                parent_options[label] = p['id']
            
            if is_new:
                p_mode = st.radio("保護者の登録方法", ["既存の保護者から選択", "新しく保護者を登録"], horizontal=True, index=1)
                if p_mode == "既存の保護者から選択":
                    sel_p_name = st.selectbox("保護者を選択", options=list(parent_options.keys()))
                else:
                    st.markdown("**■ 保護者1（メイン）**")
                    col_p1, col_p2 = st.columns(2)
                    with col_p1: p_name_val = st.text_input("氏名 ※必須", key="p1_new_n")
                    with col_p2: 
                        p_email_val = st.text_input("メールアドレス", key="p1_new_e")
                        p_phone_val = st.text_input("電話番号", key="p1_new_p")
                    st.markdown("**■ 保護者2（サブ・任意）**")
                    col_p3, col_p4 = st.columns(2)
                    with col_p3: p_name_val_2 = st.text_input("氏名", key="p2_new_n")
                    with col_p4: 
                        p_email_val_2 = st.text_input("メールアドレス", key="p2_new_e")
                        p_phone_val_2 = st.text_input("電話番号", key="p2_new_p")
            else:
                st.info("💡 下記の内容を書き換えると、登録済みの保護者情報が直接更新されます。")
                st.markdown("**■ 保護者1（メイン）**")
                col_p1, col_p2 = st.columns(2)
                with col_p1: p_name_val = st.text_input("氏名 ※必須", value=target_parent.get('name', ''), key="p1_edit_n")
                with col_p2: 
                    p_email_val = st.text_input("メールアドレス", value=target_parent.get('email', ''), key="p1_edit_e")
                    p_phone_val = st.text_input("電話番号", value=target_parent.get('phone', ''), key="p1_edit_p")
                st.markdown("**■ 保護者2（サブ・任意）**")
                col_p3, col_p4 = st.columns(2)
                with col_p3: p_name_val_2 = st.text_input("氏名", value=target_parent.get('name_2', ''), key="p2_edit_n")
                with col_p4: 
                    p_email_val_2 = st.text_input("メールアドレス", value=target_parent.get('email_2', ''), key="p2_edit_e")
                    p_phone_val_2 = st.text_input("電話番号", value=target_parent.get('phone_2', ''), key="p2_edit_p")
                    
            st.divider()

            st.subheader("🏦 引き落とし口座情報")
            acc_options = {f"{a['bank_code']}-{a['account_number']} ({a['account_name_kana']})": a['id'] for a in accounts_data}
            
            if is_new:
                a_mode = st.radio("口座の登録方法", ["既存の口座から選択", "新しく口座を登録"], horizontal=True, index=1)
                if a_mode == "既存の口座から選択":
                    sel_a_label = st.selectbox("口座を選択", options=list(acc_options.keys()))
                else:
                    col_a1, col_a2 = st.columns(2)
                    with col_a1:
                        a_b_code = st.text_input("銀行コード (4桁)")
                        a_br_code = st.text_input("支店コード (3桁)")
                        a_type = st.selectbox("預金種目", ["1 (普通)", "2 (当座)"])
                    with col_a2:
                        a_num = st.text_input("口座番号 (7桁)")
                        a_kana = st.text_input("口座名義カナ（全角ひらがな入力OK）")
            else:
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    a_b_code = st.text_input("銀行コード (4桁)", value=target_account.get('bank_code', ''))
                    a_br_code = st.text_input("支店コード (3桁)", value=target_account.get('branch_code', ''))
                    type_val = target_account.get('account_type', '1')
                    a_type = st.selectbox("預金種目", ["1 (普通)", "2 (当座)"], index=0 if type_val == '1' else 1)
                with col_a2:
                    a_num = st.text_input("口座番号 (7桁)", value=target_account.get('account_number', ''))
                    a_kana = st.text_input("口座名義カナ（全角ひらがな入力OK）", value=target_account.get('account_name_kana', ''))
            
            st.markdown("---")
            submit_btn = st.button("💾 この内容で保存する", type="primary", use_container_width=True)
            
            if submit_btn:
                if not m_last or not m_first:
                    st.error("選手の姓名は必須です。")
                else:
                    try:
                        if m_leave and m_status == "在籍":
                            m_status = "退会"

                        if is_new:
                            if p_mode == "既存の保護者から選択":
                                final_p_id = parent_options[sel_p_name]
                            else:
                                new_p = supabase.table("parents").insert({"name": p_name_val, "email": p_email_val, "phone": p_phone_val, "name_2": p_name_val_2, "email_2": p_email_val_2, "phone_2": p_phone_val_2}).execute()
                                final_p_id = new_p.data[0]['id']
                                
                            if a_mode == "既存の口座から選択":
                                final_a_id = acc_options[sel_a_label]
                            else:
                                new_a = supabase.table("bank_accounts").insert({"parent_id": final_p_id, "bank_code": a_b_code.zfill(4), "branch_code": a_br_code.zfill(3), "account_type": a_type.split(" ")[0], "account_number": a_num.zfill(7), "account_name_kana": clean_kana(a_kana)}).execute()
                                final_a_id = new_a.data[0]['id']
                        else:
                            supabase.table("parents").update({"name": p_name_val, "email": p_email_val, "phone": p_phone_val, "name_2": p_name_val_2, "email_2": p_email_val_2, "phone_2": p_phone_val_2}).eq("id", target_parent['id']).execute()
                            supabase.table("bank_accounts").update({"bank_code": a_b_code.zfill(4), "branch_code": a_br_code.zfill(3), "account_type": a_type.split(" ")[0], "account_number": a_num.zfill(7), "account_name_kana": clean_kana(a_kana)}).eq("id", target_account['id']).execute()
                            final_p_id = target_parent['id']
                            final_a_id = target_account['id']

                        member_payload = {
                            "parent_id": final_p_id, "account_id": final_a_id,
                            "last_name": m_last, "first_name": m_first,
                            "birthdate": str(m_dob) if m_dob else None, "category": calc_cat,
                            "status": m_status, "base_monthly_fee": m_fee if is_custom else get_auto_fee(calc_cat),
                            "is_custom_fee": use_custom_fee,
                            "join_date": str(m_join) if m_join else None, "leave_date": str(m_leave) if m_leave else None
                        }

                        if is_new:
                            supabase.table("members").insert(member_payload).execute()
                            st.success("新規選手の登録が完了しました！")
                        else:
                            supabase.table("members").update(member_payload).eq("id", target_member['id']).execute()
                            st.success("選手情報（および保護者・口座情報）の更新が完了しました！")
                        
                        st.cache_data.clear()
                        st.session_state.current_view = 'list'
                        st.session_state.selected_member_id = None
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"保存中にエラーが発生しました: {e}")

        if not is_new and st.session_state.user_role == 'admin':
            st.markdown("---")
            with st.expander("⚠️ 危険な操作 (選手データの完全削除)"):
                st.write("この選手データをシステムから完全に削除します。過去の請求履歴も消去されます。（※退会扱いにしたい場合は、上のステータスを「退会」にして保存してください）")
                
                if st.button("🗑️ この選手を完全に削除する", type="primary"):
                    try:
                        mem_id = target_member['id']
                        p_id = target_member['parent_id']
                        
                        supabase.table("billings").delete().eq("member_id", mem_id).execute()
                        supabase.table("members").delete().eq("id", mem_id).execute()
                        
                        siblings = supabase.table("members").select("id").eq("parent_id", p_id).execute()
                        
                        if len(siblings.data) == 0:
                            supabase.table("bank_accounts").delete().eq("parent_id", p_id).execute()
                            supabase.table("parents").delete().eq("id", p_id).execute()
                            st.info("💡 紐づいていた保護者データと口座データも、他の利用者がいないため同時に削除しました。")
                            
                        st.success("選手の削除が完了しました。")
                        st.cache_data.clear()
                        st.session_state.current_view = 'list'
                        st.session_state.selected_member_id = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"削除中にエラーが発生しました: {e}")

# ==========================================
# 【TAB 2】請求データ生成 (全銀出力) 
# ==========================================
elif selected_tab == "💰 請求データ生成 (全銀出力)":
    st.header("💰 請求データの生成（全銀ファイル出力）")
    st.write("選手マスタに登録されている現在の金額と、過去の未落ち分を自動計算し、今月分の請求データを作成します。")
    
    with st.expander("🏦 クラブ（委託者）の口座設定", expanded=False):
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            club_code = st.text_input("委託者コード（10桁）", value="0000000000")
            club_name = st.text_input("委託者名（半角カナ40桁以内）", value="ﾌﾞﾘｵﾍﾞｯｶｳﾗﾔｽ")
            withdraw_date = st.text_input("引落日（MMDD・4桁）", value="0427")
        with col_c2:
            club_bank_code = st.text_input("引落銀行番号（4桁）", value="0001")
            club_branch_code = st.text_input("引落支店番号（3桁）", value="001")
            club_acc_type = st.selectbox("引落預金種目", ["1 (普通)", "2 (当座)"])
            club_acc_num = st.text_input("引落口座番号（7桁）", value="1234567")

    st.divider()
    target_month = st.text_input("作成する請求年月", value=datetime.now().strftime("%Y-%m"))
    
    if st.button("🔍 今月の請求データを計算・作成する", type="primary"):
        st.session_state.show_billing_data = True
        
    if st.session_state.show_billing_data:
        if not members_data or not accounts_data:
            st.warning("データがありません。")
        else:
            df_members = pd.DataFrame(members_data)
            df_accounts = pd.DataFrame(accounts_data)
            active_members = df_members[df_members['status'] == '在籍']
            
            if active_members.empty:
                st.info("請求対象の選手がいません。")
            else:
                df_target = pd.merge(active_members, df_accounts, left_on='account_id', right_on='id', suffixes=('_member', '_acc'))
                df_target['選手名'] = df_target['last_name'] + ' ' + df_target['first_name']
                
                df_billings = pd.DataFrame(billings_data) if billings_data else pd.DataFrame(columns=['member_id', 'is_paid', 'total_amount', 'billing_month'])
                
                billing_records_to_insert = []
                display_data = []
                total_claim_amount = 0
                
                for idx, row in df_target.iterrows():
                    m_id = row['id_member']
                    base_fee = int(row['base_monthly_fee'])
                    current_cat = row['category']
                    carryover = 0
                    
                    if not df_billings.empty:
                        unpaid_records = df_billings[(df_billings['member_id'] == m_id) & (df_billings['is_paid'] == False) & (df_billings['billing_month'] != target_month)]
                        if not unpaid_records.empty:
                            carryover = int(unpaid_records['total_amount'].sum())
                            
                    total_fee = base_fee + carryover
                    total_claim_amount += total_fee
                    
                    display_data.append({
                        '選手名': row['選手名'],
                        '請求カテゴリ': f"{current_cat} {'(手動)' if row.get('is_custom_fee', False) else ''}",
                        '当月基本額': base_fee,
                        '未落ち繰越額': carryover,
                        '今回請求額': total_fee,
                        '口座名義カナ': row['account_name_kana']
                    })
                    
                    billing_records_to_insert.append({
                        "member_id": m_id, "billing_month": target_month,
                        "base_amount": base_fee, "carryover_amount": carryover,
                        "total_amount": total_fee, "is_paid": False
                    })
                
                df_display = pd.DataFrame(display_data)
                
                st.write(f"### 対象者: {len(df_display)}名 / 今回の総請求額: ¥{total_claim_amount:,}")
                st.dataframe(df_display, use_container_width=True)
                
                zengin_lines = []
                header = "1" + "91" + "0" + pad_str(club_code, 10) + pad_str(club_name, 40) + pad_num(withdraw_date, 4) + pad_num(club_bank_code, 4) + pad_str("", 15) + pad_num(club_branch_code, 3) + pad_str("", 15) + pad_num(club_acc_type.split(" ")[0], 1) + pad_num(club_acc_num, 7) + pad_str("", 17)
                zengin_lines.append(header)
                
                for idx, row in df_target.iterrows():
                    total_fee = next(item['今回請求額'] for item in display_data if item['選手名'] == row['選手名'])
                    record = "2" + pad_num(row['bank_code'], 4) + pad_str("", 15) + pad_num(row['branch_code'], 3) + pad_str("", 15) + pad_str("", 4) + pad_num(row['account_type'], 1) + pad_num(row['account_number'], 7) + pad_str(row['account_name_kana'], 30) + pad_num(total_fee, 10) + "0" + pad_str(str(row['id_member']).replace("-", "")[:20], 20) + "0" + pad_str("", 8)
                    zengin_lines.append(record)
                
                trailer = "8" + pad_num(len(df_target), 6) + pad_num(total_claim_amount, 12) + pad_num(0, 6) + pad_num(0, 12) + pad_num(0, 6) + pad_num(0, 12) + pad_str("", 65)
                zengin_lines.append(trailer)
                zengin_lines.append("9" + pad_str("", 119))
                zengin_text = "\r\n".join(zengin_lines)
                
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.info("💡 ダウンロードと同時に、今回の請求履歴がデータベースに保存されます。（すでに保存済みの場合は上書きされます）")
                with col_d2:
                    file_name = f"zengin_billing_{target_month}.txt"
                    def save_billings_to_db():
                        try:
                            supabase.table("billings").delete().eq("billing_month", target_month).execute()
                            supabase.table("billings").insert(billing_records_to_insert).execute()
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"DB保存エラー: {e}")

                    st.download_button(
                        label=f"📥 銀行アップロード用ファイル（{file_name}）をダウンロード",
                        data=zengin_text.encode('shift_jis', errors='replace'),
                        file_name=file_name, mime="text/plain",
                        on_click=save_billings_to_db, type="primary"
                    )

# ==========================================
# 🌟【TAB 3】引落結果の取込 (消込) ＋ 手動マッチング学習機能
# ==========================================
elif selected_tab == "💳 引落結果の取込 (消込)":
    st.header("💳 銀行からの引落結果の取込（自動消込）")
    target_month_import = st.text_input("消込を行う請求年月", value=datetime.now().strftime("%Y-%m"), key="import_month")
    
    uploaded_result = st.file_uploader("引落結果CSVファイルを選択", type=["csv"])
    if uploaded_result is not None:
        try:
            try: df_result = pd.read_csv(uploaded_result, encoding='shift_jis', header=None)
            except: 
                uploaded_result.seek(0)
                df_result = pd.read_csv(uploaded_result, encoding='utf-8', header=None)
            
            df_data = df_result[df_result[0] == 2].copy()
            df_data.columns = ['データ区分', '銀行コード', '支店コード', '預金種目', '口座番号', '銀行名カナ', '支店名カナ', '口座名義カナ', '引落金額', '新規コード', '顧客番号', '結果コード']
            
            st.write(f"読み込み件数: **{len(df_data)}件**")
            
            if st.button("🚀 自動消込を実行する", type="primary"):
                st.session_state.last_imported_month = target_month_import
                progress_bar = st.progress(0)
                total_rows = len(df_data)
                success_count, unpaid_count, error_count = 0, 0, 0
                df_acc = pd.DataFrame(accounts_data)
                
                unmatched_list = [] # 迷子データを溜めるリスト
                
                for i, (idx, row) in enumerate(df_data.iterrows()):
                    acc_num = str(row['口座番号']).zfill(7)
                    acc_kana = clean_kana(str(row['口座名義カナ']).strip())
                    result_code = str(row['結果コード']).strip()
                    b_code = str(row['銀行コード']).zfill(4)
                    br_code = str(row['支店コード']).zfill(3)
                    amount_val = row['引落金額']
                    
                    match_acc = df_acc[(df_acc['account_number'] == acc_num) & (df_acc['account_name_kana'] == acc_kana)]
                    if not match_acc.empty:
                        target_acc_id = match_acc.iloc[0]['id']
                        target_member = next((m for m in members_data if m['account_id'] == target_acc_id), None)
                        
                        if target_member:
                            member_id = target_member['id']
                            is_paid_flag = (result_code == '0')
                            try:
                                supabase.table("billings").update({"is_paid": is_paid_flag, "zengin_result_code": result_code}).eq("member_id", member_id).eq("billing_month", target_month_import).execute()
                                if is_paid_flag: success_count += 1
                                else: unpaid_count += 1
                            except: error_count += 1
                        else: error_count += 1 
                    else:
                        error_count += 1 
                        # 🌟 迷子データをリストに追加する
                        unmatched_list.append({
                            'bank_code': b_code,
                            'branch_code': br_code,
                            'account_number': acc_num,
                            'account_name_kana': acc_kana,
                            'result_code': result_code,
                            'amount': amount_val
                        })
                    
                    progress_bar.progress(min((i + 1) / total_rows, 1.0))
                
                st.session_state.unmatched_records = unmatched_list
                st.cache_data.clear()
                st.success(f"🎉 自動消込が完了しました！ (引落成功: {success_count}件 / 残高不足等: {unpaid_count}件 / 突合エラー・迷子: {error_count}件)")

        except Exception as e:
            st.error(f"ファイルの読み込みに失敗しました。エラー詳細: {e}")

    # 🌟 手動マッチング（学習）UIの表示
    if st.session_state.unmatched_records:
        st.divider()
        st.subheader("⚠️ 手動マッチング (表記ズレの修正・学習)")
        st.write("システム内の登録とカナ名義などが完全一致しなかったデータです。該当する選手を選んで紐づけると、次回から自動でマッチングされるように学習（データの上書き）します。")
        
        # プルダウン用の選択肢を作成
        member_options = {"選択してください": None}
        if members_data:
            for m in members_data:
                if m['status'] == '在籍':
                    a = next((acc for acc in accounts_data if acc['id'] == m['account_id']), None)
                    curr_kana = a['account_name_kana'] if a else "未登録"
                    label = f"[{m['category']}] {m['last_name']} {m['first_name']} (現在の登録: {curr_kana})"
                    member_options[label] = m['id']

        for idx, u_rec in enumerate(st.session_state.unmatched_records):
            with st.expander(f"🔴 迷子データ: {u_rec['account_name_kana']} (口座: {u_rec['account_number']} / 結果コード: {u_rec['result_code']} / 金額: ¥{int(u_rec['amount'])})", expanded=True):
                col_m1, col_m2 = st.columns([3, 1])
                with col_m1:
                    selected_label = st.selectbox("このデータの正しい選手は誰ですか？", options=list(member_options.keys()), key=f"unmatched_sel_{idx}")
                with col_m2:
                    st.write("")
                    if st.button("手動で紐づける", key=f"unmatched_btn_{idx}", type="primary"):
                        if selected_label == "選択してください":
                            st.error("選手を選択してください。")
                        else:
                            target_member_id = member_options[selected_label]
                            target_member = next((m for m in members_data if m['id'] == target_member_id), None)
                            imported_month = st.session_state.get('last_imported_month', target_month_import)

                            if target_member:
                                is_paid_flag = (u_rec['result_code'] == '0')
                                try:
                                    # 1. 今月の消込を完了させる
                                    supabase.table("billings").update({
                                        "is_paid": is_paid_flag,
                                        "zengin_result_code": u_rec['result_code']
                                    }).eq("member_id", target_member_id).eq("billing_month", imported_month).execute()

                                    # 2. 口座情報を「銀行の正解データ」で上書き学習させる！
                                    supabase.table("bank_accounts").update({
                                        "account_name_kana": clean_kana(u_rec['account_name_kana']),
                                        "account_number": u_rec['account_number'],
                                        "bank_code": u_rec['bank_code'],
                                        "branch_code": u_rec['branch_code']
                                    }).eq("id", target_member['account_id']).execute()

                                    st.success(f"✅ {target_member['last_name']}選手の口座情報を学習し、消込を完了しました！")
                                    st.session_state.unmatched_records.pop(idx)
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"エラーが発生しました: {e}")

    st.divider()
    st.subheader("📋 消込結果・請求履歴の確認")
    
    if billings_data:
        df_b = pd.DataFrame(billings_data)
        df_m = pd.DataFrame(members_data)[['id', 'last_name', 'first_name', 'category']]
        df_m['選手名'] = df_m['last_name'] + ' ' + df_m['first_name']
        
        df_disp = pd.merge(df_b, df_m, left_on='member_id', right_on='id', how='left')
        
        month_options = sorted(df_disp['billing_month'].dropna().unique().tolist(), reverse=True)
        
        if month_options:
            col_m, col_s = st.columns(2)
            with col_m:
                selected_month = st.selectbox("確認する請求年月", options=month_options)
            with col_s:
                status_filter = st.selectbox("抽出条件", options=["すべて", "引落成功 (済)", "引落不能 (未払い・繰越)"])
                
            df_filtered = df_disp[df_disp['billing_month'] == selected_month].copy()
            
            if status_filter == "引落成功 (済)":
                df_filtered = df_filtered[df_filtered['is_paid'] == True]
            elif status_filter == "引落不能 (未払い・繰越)":
                df_filtered = df_filtered[df_filtered['is_paid'] == False]
                
            if not df_filtered.empty:
                st.write(f"該当件数: {len(df_filtered)}件")
                df_filtered['ステータス'] = df_filtered['is_paid'].apply(lambda x: "🟢 成功" if x else "🔴 不能(未払)")
                df_filtered['請求額'] = df_filtered['total_amount'].apply(lambda x: f"¥{int(x):,}" if pd.notna(x) else "-")
                df_filtered['結果コード'] = df_filtered['zengin_result_code'].fillna('-')
                
                display_cols = ['選手名', 'category', 'ステータス', '請求額', '結果コード']
                st.dataframe(df_filtered[display_cols], use_container_width=True)
            else:
                st.info("指定した条件に該当するデータがありません。")
    else:
        st.info("請求履歴データがありません。「請求データ生成」からダウンロードを実行すると履歴が作られます。")

# ==========================================
# 【TAB 4】システム管理 (入出力・年度更新) 
# ==========================================
elif selected_tab == "⚙️ システム管理 (入出力・年度更新)":
    st.header("⚙️ システム管理・データ入出力")
    
    if st.session_state.user_role == 'admin':
        st.subheader("🌸 年度切り替え・卒団処理 (管理者専用)")
        with st.expander("⚠️ 処理メニューを開く (実行するとデータベースが一括更新されます)", expanded=True):
            
            st.markdown("#### 🎓 1月実施: U-18 卒団生（高校3年生）の自動退会処理")
            if st.button("U-18 卒団処理を実行する", type="primary"):
                today = datetime.now().date()
                current_sy_year = today.year if today.month >= 4 else today.year - 1
                
                target_date_for_grad = date(current_sy_year, 10, 1)
                grad_count = 0
                for m in members_data:
                    if m['status'] == '在籍' and m['category'] == 'U-18':
                        dob = datetime.strptime(m['birthdate'], '%Y-%m-%d').date() if m['birthdate'] else None
                        if dob:
                            age_curr, _ = calculate_age_and_category(dob, target_date_for_grad)
                            if age_curr is not None and age_curr >= 18:
                                leave_d = f"{current_sy_year}-12-31"
                                supabase.table("members").update({"status": "退会", "leave_date": leave_d}).eq("id", m['id']).execute()
                                grad_count += 1
                st.success(f"🎉 {grad_count}名の高3選手を卒団（12月末退会）処理しました！")
                st.cache_data.clear()
            
            st.divider()
            
            st.markdown("#### 🌸 3月末実施: 新年度マスタ一括更新（4/1基準）")
            default_update_year = datetime.now().year if datetime.now().month >= 4 else datetime.now().year - 1
            update_year = st.number_input("更新対象の年度 (例: 2025年度向けなら「2025」)", value=default_update_year, step=1)
            
            if st.button(f"{update_year}年度版にマスタを一括更新する", type="primary"):
                target_date_for_new = date(update_year, 10, 1)
                update_count = 0
                for m in members_data:
                    if m['status'] == '在籍':
                        dob = datetime.strptime(m['birthdate'], '%Y-%m-%d').date() if m['birthdate'] else None
                        if dob:
                            _, new_cat = calculate_age_and_category(dob, target_date_for_new)
                            update_payload = {"category": new_cat}
                            is_custom = m.get('is_custom_fee')
                            if str(is_custom).lower() != 'true':
                                update_payload["base_monthly_fee"] = int(get_auto_fee(new_cat))
                            supabase.table("members").update(update_payload).eq("id", m['id']).execute()
                            update_count += 1
                st.success(f"🎉 {update_count}名の選手データを{update_year}年度版の学年・会費に更新しました！")
                st.cache_data.clear()
        
    st.markdown("---")
    
    st.subheader("📤 現在のデータをエクスポート")
    if members_data and parents_data and accounts_data:
        df_m_exp = pd.DataFrame(members_data)
        df_p_exp = pd.DataFrame(parents_data)
        df_a_exp = pd.DataFrame(accounts_data)
        df_export = pd.merge(df_m_exp, df_p_exp, left_on='parent_id', right_on='id', suffixes=('_member', '_parent'))
        df_export = pd.merge(df_export, df_a_exp, left_on='account_id', right_on='id', suffixes=('', '_account'))
        
        export_columns = {
            'last_name': '選手姓', 'first_name': '選手名', 'birthdate': '生年月日', 
            'category': 'カテゴリ', 'status': 'ステータス', 'base_monthly_fee': '基本月会費', 'is_custom_fee': '手動料金フラグ',
            'join_date': '入会日', 'leave_date': '退会日',
            'name': '保護者1氏名', 'email': '保護者1メール', 'phone': '保護者1電話',
            'name_2': '保護者2氏名', 'email_2': '保護者2メール', 'phone_2': '保護者2電話',
            'bank_code': '銀行コード', 'branch_code': '支店コード', 'account_type': '預金種目', 
            'account_number': '口座番号', 'account_name_kana': '口座名義カナ'
        }
        df_export_final = df_export[list(export_columns.keys())].rename(columns=export_columns)
        csv_data = df_export_final.to_csv(index=False).encode('utf-8-sig')
        st.download_button(label="📊 現在の全データをCSVでダウンロード", data=csv_data, file_name=f"club_members_export_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")

    st.divider()

    st.subheader("📥 新規データの一括インポート (上書き更新対応)")
    uploaded_file = st.file_uploader("CSVファイルを選択してください", type=["csv"])
    if uploaded_file is not None:
        try:
            df_import = pd.read_csv(uploaded_file)
            st.write(f"読み込み件数: **{len(df_import)}件**")
            
            if st.button("🚀 このデータで一括登録・更新を開始する", type="primary"):
                progress_bar = st.progress(0)
                total_rows = len(df_import)
                success_count = 0
                
                for i, (idx, row) in enumerate(df_import.iterrows()):
                    def get_val(col_name):
                        val = row.get(col_name, '')
                        return '' if pd.isna(val) else str(val).strip()

                    try:
                        p1_name = get_val('保護者1氏名')
                        if not p1_name: continue 
                        
                        existing_p = next((p for p in parents_data if p['name'] == p1_name), None) if parents_data else None
                        if existing_p:
                            final_p_id = existing_p['id']
                            supabase.table("parents").update({"email": get_val('保護者1メール'), "phone": get_val('保護者1電話'), "name_2": get_val('保護者2氏名'), "email_2": get_val('保護者2メール'), "phone_2": get_val('保護者2電話')}).eq("id", final_p_id).execute()
                        else:
                            new_p = supabase.table("parents").insert({"name": p1_name, "email": get_val('保護者1メール'), "phone": get_val('保護者1電話'), "name_2": get_val('保護者2氏名'), "email_2": get_val('保護者2メール'), "phone_2": get_val('保護者2電話')}).execute()
                            final_p_id = new_p.data[0]['id']
                        
                        a_num = get_val('口座番号').zfill(7) if get_val('口座番号') else '0000000'
                        a_kana = clean_kana(get_val('口座名義カナ'))
                        existing_a = next((a for a in accounts_data if a['account_number'] == a_num and a['account_name_kana'] == a_kana), None) if accounts_data else None
                        
                        if existing_a:
                            final_a_id = existing_a['id']
                        else:
                            b_code = get_val('銀行コード').zfill(4) if get_val('銀行コード') else '0000'
                            br_code = get_val('支店コード').zfill(3) if get_val('支店コード') else '000'
                            a_type = '2' if '2' in get_val('預金種目') or '当座' in get_val('預金種目') else '1'
                            new_a = supabase.table("bank_accounts").insert({"parent_id": final_p_id, "bank_code": b_code, "branch_code": br_code, "account_type": a_type, "account_number": a_num, "account_name_kana": a_kana}).execute()
                            final_a_id = new_a.data[0]['id']
                        
                        m_last, m_first = get_val('選手姓'), get_val('選手名')
                        existing_m = next((m for m in members_data if m['last_name'] == m_last and m['first_name'] == m_first), None) if members_data else None
                        
                        dob_raw = get_val('生年月日')
                        dob_val = pd.to_datetime(dob_raw).strftime('%Y-%m-%d') if dob_raw else None
                        _, calc_cat = calculate_age_and_category(pd.to_datetime(dob_raw).date() if dob_val else None)
                        
                        fee_raw = get_val('基本月会費')
                        fee_val = int(float(fee_raw)) if fee_raw and fee_raw.replace('.','').isdigit() else (get_auto_fee(calc_cat) if calc_cat else 12000)
                        
                        join_raw, leave_raw = get_val('入会日'), get_val('退会日')
                        
                        member_payload = {
                            "parent_id": final_p_id, "account_id": final_a_id,
                            "birthdate": dob_val, "category": calc_cat,
                            "status": get_val('ステータス') or '在籍', "base_monthly_fee": fee_val,
                            "is_custom_fee": False, 
                            "join_date": pd.to_datetime(join_raw).strftime('%Y-%m-%d') if join_raw else None, 
                            "leave_date": pd.to_datetime(leave_raw).strftime('%Y-%m-%d') if leave_raw else None
                        }
                        
                        if existing_m:
                            supabase.table("members").update(member_payload).eq("id", existing_m['id']).execute()
                        else:
                            member_payload["last_name"] = m_last
                            member_payload["first_name"] = m_first
                            supabase.table("members").insert(member_payload).execute()
                        
                        success_count += 1
                    except Exception as e:
                        st.error(f"{idx+1}行目エラー: {e}")
                    
                    progress_bar.progress(min((i + 1) / total_rows, 1.0))
                
                st.success(f"🎉 {success_count}件のデータを一括登録・更新しました！")
                st.cache_data.clear()
        except Exception as e:
            st.error("エラーが発生しました。")

# ==========================================
# 【TAB 5】ダッシュボード (経営分析)
# ==========================================
elif selected_tab == "📊 ダッシュボード":
    st.header("📊 クラブ経営・分析ダッシュボード")
    
    if not members_data:
        st.info("データがありません。「選手名簿管理」から選手を登録してください。")
    else:
        df_m = pd.DataFrame(members_data)
        df_active = df_m[df_m['status'] == '在籍']
        
        # 指標の計算
        total_members = len(df_active)
        expected_revenue = df_active['base_monthly_fee'].sum() if not df_active.empty else 0
        
        df_b = pd.DataFrame(billings_data) if billings_data else pd.DataFrame(columns=['is_paid', 'total_amount'])
        unpaid_total = 0
        if not df_b.empty:
            unpaid_total = df_b[df_b['is_paid'] == False]['total_amount'].sum()
            
        # 3つの主要KPI表示
        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        col_kpi1.metric(label="👥 現在の総在籍人数", value=f"{total_members} 名")
        col_kpi2.metric(label="💰 今月の見込み会費売上", value=f"¥{int(expected_revenue):,}")
        col_kpi3.metric(label="⚠️ 現在の未収金総額", value=f"¥{int(unpaid_total):,}")
        
        st.divider()
        
        # グラフ表示
        if not df_active.empty:
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                st.subheader("📈 カテゴリ別 在籍人数")
                # カテゴリの順序を定義してソート
                cat_order = ["U-6", "U-7", "U-8", "U-9", "U-10", "U-11", "U-12", "U-13", "U-14", "U-15", "U-18", "トップ"]
                df_active['category'] = pd.Categorical(df_active['category'], categories=cat_order, ordered=True)
                cat_counts = df_active['category'].value_counts().sort_index().reset_index()
                cat_counts.columns = ['カテゴリ', '人数']
                # 0人のカテゴリは除外
                cat_counts = cat_counts[cat_counts['人数'] > 0]
                st.bar_chart(cat_counts.set_index('カテゴリ'), use_container_width=True)
                
            with col_chart2:
                st.subheader("💴 カテゴリ別 見込み売上構成")
                cat_sales = df_active.groupby('category', observed=False)['base_monthly_fee'].sum().reset_index()
                cat_sales.columns = ['カテゴリ', '売上(円)']
                # 0円のカテゴリは除外
                cat_sales = cat_sales[cat_sales['売上(円)'] > 0]
                st.bar_chart(cat_sales.set_index('カテゴリ'), use_container_width=True)

# ==========================================
# 【TAB 6】アカウント設定 (パスワード変更)
# ==========================================
elif selected_tab == "⚙️ アカウント設定":
    st.header("⚙️ アカウント設定")
    st.write("ログイン用のパスワードを変更できます。定期的な変更をおすすめします。")

    with st.container():
        st.info("💡 変更後、次回システムを開く際は新しいパスワードでログインしてください。")
        
        with st.form("password_change_form"):
            new_password = st.text_input("新しいパスワード (6文字以上推奨)", type="password")
            new_password_confirm = st.text_input("新しいパスワード (確認用)", type="password")
            
            submit_btn = st.form_submit_button("パスワードを変更する", type="primary")

            if submit_btn:
                if len(new_password) < 6:
                    st.error("パスワードは6文字以上で入力してください。")
                elif new_password != new_password_confirm:
                    st.error("確認用パスワードが一致しません。もう一度入力してください。")
                else:
                    try:
                        response = supabase.auth.update_user({"password": new_password})
                        if response.user:
                            st.success("🎉 パスワードを正常に変更しました！")
                        else:
                            st.error("パスワードの変更に失敗しました。")
                    except Exception as e:
                        st.error(f"エラーが発生しました: {e}")