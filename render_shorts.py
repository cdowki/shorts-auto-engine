import os
import json
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload

def upload_to_google_drive(file_path, folder_id):
    """
    구글 서비스 계정으로 드라이브에 영상을 업로드하고,
    개인 계정(cdowki@gmail.com)으로 소유권을 이전하여 스토리지 쿼터 에러를 원천 차단합니다.
    """
    SCOPES = ['https://www.googleapis.com/auth/drive']
    
    # 환경 변수(GitHub Secrets)에서 서비스 계정 JSON 정보 로드
    creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    
    if creds_json:
        creds_info = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    else:
        # 로컬 테스트용 파일 경로 대응
        credentials = service_account.Credentials.from_service_account_file('credentials.json', scopes=SCOPES)

    service = build('drive', 'v3', credentials=credentials)

    file_metadata = {
        'name': os.path.basename(file_path),
        'parents': [folder_id]
    }
    
    media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True)

    try:
        # 1. 파일 업로드 실행 (supportsAllDrives 옵션 포함)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
        
        file_id = file.get('id')
        print(f"✅ 구글 드라이브 업로드 성공! 파일 ID: {file_id}")
        
        # 2. 개인 계정(cdowki@gmail.com)으로 파일 소유권 이전 (용량 제한 우회 핵심 로직)
        try:
            permission = {
                'type': 'user',
                'role': 'owner',
                'emailAddress': 'cdowki@gmail.com'
            }
            service.permissions().create(
                fileId=file_id,
                body=permission,
                transferOwnership=True,
                sendNotificationEmail=False,
                supportsAllDrives=True
            ).execute()
            print("👤 파일 소유권이 개인 계정(cdowki@gmail.com)으로 성공적으로 이전되었습니다.")
        except Exception as perm_error:
            print(f"⚠️ 소유권 이전 경고 (공유 폴더 권한에 따라 다를 수 있음): {perm_error}")

        return file.get('webViewLink')

    except Exception as e:
        print(f"❌ 구글 드라이브 업로드 중 오류 발생: {e}")
        raise e

if __name__ == "__main__":
    # 로컬 테스트 혹은 파이프라인 실행부 예시
    target_file = "output_shorts.mp4"
    target_folder_id = os.environ.get('DRIVE_FOLDER_ID')
    
    if os.path.exists(target_file) and target_folder_id:
        upload_to_google_drive(target_file, target_folder_id)
    else:
        print("⚠️ 업로드할 파일이 없거나 DRIVE_FOLDER_ID 환경 변수가 설정되지 않았습니다.")
