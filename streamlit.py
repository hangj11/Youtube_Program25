# streamlit.py

import streamlit as st
from googleapiclient.discovery import build

# YouTube API 키 설정
# TODO: 사용자에게 API 키를 입력받도록 하거나 환경 변수에서 로드하도록 변경
API_KEY = "AIzaSyCavd8N61fB8-5I7wGqK5YSKAgRoCcAvqE"

# YouTube 데이터 API 서비스 객체 생성
youtube = build('youtube', 'v3', developerKey=API_KEY)

def get_trending_videos(region_code='KR', max_results=30):
    """지정된 지역의 YouTube 인기 동영상을 가져옵니다."""
    request = youtube.videos().list(
        part='snippet,contentDetails,statistics',
        chart='mostPopular',
        regionCode=region_code,
        maxResults=max_results
    )
    response = request.execute()

    videos = []
    for item in response['items']:
        video_id = item['id']
        title = item['snippet']['title']
        channel_title = item['snippet']['channelTitle']
        view_count = item['statistics'].get('viewCount', 0)
        like_count = item['statistics'].get('likeCount', 0)
        comment_count = item['statistics'].get('commentCount', 0)
        thumbnail_url = item['snippet']['thumbnails']['high']['url']

        videos.append({
            'video_id': video_id,
            'title': title,
            'channel_title': channel_title,
            'view_count': int(view_count),
            'like_count': int(like_count),
            'comment_count': int(comment_count),
            'thumbnail_url': thumbnail_url
        })
    return videos

st.title('YouTube 인기 동영상 TOP 30')

# 지역 코드 선택 (한국 기본값)
region = st.sidebar.selectbox('지역을 선택하세요', ['KR', 'US', 'JP', 'GB', 'IN'], index=0)

if API_KEY == "YOUR_API_KEY":
    st.warning("YouTube API 키를 `streamlit.py` 파일에 입력하거나 환경 변수로 설정해주세요.")
else:
    try:
        trending_videos = get_trending_videos(region_code=region)

        if trending_videos:
            st.subheader(f'{region} 지역의 인기 동영상')
            for video in trending_videos:
                st.write(f"**{video['title']}** by {video['channel_title']}")
                st.write(f"조회수: {video['view_count']:,}회, 좋아요: {video['like_count']:,}개, 댓글: {video['comment_count']:,}개")
                st.image(video['thumbnail_url'], width=300)
                st.markdown(f"[영상 보러가기](https://www.youtube.com/watch?v={video['video_id']})")
                st.markdown("--- недостаточно --- ")
        else:
            st.write('인기 동영상을 불러오지 못했습니다. API 키나 네트워크 연결을 확인해주세요.')
    except Exception as e:
        st.error(f"오류 발생: {e}. API 키가 유효한지 확인하고, 할당량이 초과되지 않았는지 확인해주세요.")
