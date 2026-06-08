# Streamlit Community Cloud 배포 페이지를 엽니다 (저장소·브랜치·메인 파일 자동 입력).
$deployUrl = "https://share.streamlit.io/deploy?repository=livedevgit-dev/yudoye-study&branch=main&mainModule=streamlit_app.py"
Write-Host "배포 페이지를 엽니다:" -ForegroundColor Cyan
Write-Host $deployUrl
Write-Host ""
Write-Host "브라우저에서:" -ForegroundColor Yellow
Write-Host "  1. GitHub로 로그인 (최초 1회)"
Write-Host "  2. 저장소 livedevgit-dev/yudoye-study 확인"
Write-Host "  3. Main file: streamlit_app.py 확인"
Write-Host "  4. Deploy 클릭"
Write-Host ""
Start-Process $deployUrl
