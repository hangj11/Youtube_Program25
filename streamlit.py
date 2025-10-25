# streamlit.py
# Updated: 2025-10-25
# 변경사항:
# - 하드코딩된 YouTube API 키 제거 -> 환경 변수 YT_API_KEY 사용
# - 업로드된(선택된) 영상에 대해 상세 정보(설명, 상위 댓글)를 가져오는 함수 추가
# - OpenAI 키(환경 변수 OPENAI_API_KEY)가 있으면 ChatGPT를 호출하여 질문에 답변하는 챗봇 기능 추가
# - OpenAI 키가 없으면 간단한 키워드 기반 검색으로 관련 문장을 반환하는 폴백 로직 추가
# - "Top30 목록을 컨텍스트에 포함" 옵션 추가 (목록 기반 질문 대응)
# - 에러 처리 및 캐시 적용

import os
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Optional OpenAI integration for better chatbot answers
try:
    import openai
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

# YouTube API 키를 환경변수에서 로드
API_KEY = os.getenv("YT_API_KEY", None)

if OPENAI_AVAILABLE:
    openai_api_key = os.getenv("OPENAI_API_KEY", None)
    if openai_api_key:
        openai.api_key = openai_api_key
    else:
        # If openai is installed but no key provided, treat as not available for usage.
        OPENAI_AVAILABLE = False

if API_KEY is not None:
    youtube = build('youtube', 'v3', developerKey=API_KEY)
else:
    youtube = None

st.set_page_config(page_title="YouTube 인기 동영상 + 챗봇", layout="wide")
st.title('YouTube 인기 동영상 TOP 30 & 비디오 챗봇')

# Sidebar: 설정
st.sidebar.header("설정")
region = st.sidebar.selectbox('지역을 선택하세요', ['KR', 'US', 'JP', 'GB', 'IN'], index=0)
use_openai = st.sidebar.checkbox('OpenAI로 챗봇 사용 (OPENAI_API_KEY 필요)', value=False)
include_top30_context = st.sidebar.checkbox('Top30 목록을 챗봇 컨텍스트에 포함', value=True)
if use_openai and not OPENAI_AVAILABLE:
    st.sidebar.warning("OpenAI 패키지/키가 설정되어 있지 않습니다. 환경변수 OPENAI_API_KEY를 설정하거나 OpenAI SDK를 설치하세요.")
st.sidebar.markdown("앱은 환경변수 YT_API_KEY에서 YouTube API 키를 읽습니다.")

if API_KEY is None:
    st.error("YouTube API 키가 설정되어 있지 않습니다. 환경변수 YT_API_KEY에 키를 설정하세요.")
    st.stop()

# 캐시된 호출: 인기 동영상 가져오기
@st.cache_data(ttl=300)
def get_trending_videos(region_code='KR', max_results=30):
    """지정된 지역의 YouTube 인기 동영상을 가져옵니다."""
    try:
        request = youtube.videos().list(
            part='snippet,contentDetails,statistics',
            chart='mostPopular',
            regionCode=region_code,
            maxResults=max_results
        )
        response = request.execute()
    except HttpError as e:
        raise RuntimeError(f"YouTube API 요청 오류: {e}")

    videos = []
    for item in response.get('items', []):
        video_id = item['id']
        snippet = item.get('snippet', {})
        statistics = item.get('statistics', {})
        thumbnails = snippet.get('thumbnails', {})
        high_thumb = thumbnails.get('high') or thumbnails.get('default') or {}
        thumbnail_url = high_thumb.get('url', '')

        videos.append({
            'video_id': video_id,
            'title': snippet.get('title', ''),
            'channel_title': snippet.get('channelTitle', ''),
            'view_count': int(statistics.get('viewCount', 0)),
            'like_count': int(statistics.get('likeCount', 0)),
            'comment_count': int(statistics.get('commentCount', 0)),
            'thumbnail_url': thumbnail_url,
            'description': snippet.get('description', '')
        })
    return videos

# 비디오 상세 및 댓글 가져오기
@st.cache_data(ttl=300)
def get_video_comments(video_id, max_results=50):
    """비디오의 상위 댓글을 가져옵니다 (commentThreads 사용)."""
    comments = []
    try:
        request = youtube.commentThreads().list(
            part='snippet',
            videoId=video_id,
            maxResults=min(max_results, 100),
            textFormat='plainText',
            order='relevance'  # 또는 'time'
        )
        response = request.execute()
        for item in response.get('items', []):
            top_comment = item['snippet']['topLevelComment']['snippet']
            comments.append({
                'author': top_comment.get('authorDisplayName', ''),
                'text': top_comment.get('textDisplay', ''),
                'like_count': top_comment.get('likeCount', 0)
            })
    except HttpError:
        # 댓글 비활성화 혹은 접근권한 문제일 수 있음
        return []
    return comments

# 간단한 키워드 기반 검색 (OpenAI 없을 때 폴백)
def keyword_search_answer(query, contexts, max_snippets=5):
    """질문에 대해 context들에서 키워드를 기반으로 관련 문장들을 찾아 반환합니다."""
    q_words = set([w.lower() for w in query.split() if len(w) > 2])
    scored = []
    for ctx in contexts:
        text = ctx.get('text', '')
        # 간단 분할. 실제로는 더 정교한 전처리 필요
        text_words = set([w.lower().strip('.,?!') for w in text.split()])
        overlap = q_words.intersection(text_words)
        score = len(overlap)
        if score > 0:
            scored.append((score, ctx))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return "관련 정보를 찾지 못했습니다. 더 구체적으로 질문해 주세요.\n\n(더 좋은 답변을 원하시면 OpenAI API 키를 OPENAI_API_KEY 환경 변수에 설정하고 사이드바의 'OpenAI로 챗봇 사용'을 켜세요.)"
    snippets = []
    for _, ctx in scored[:max_snippets]:
        source = ctx.get('source', 'context')
        text = ctx.get('text', '')
        snippets.append(f"[{source}] {text}")
    return "관련 문장:\n\n" + "\n\n---\n\n".join(snippets)

# OpenAI 기반 답변 생성
def openai_chat_answer(question, contexts):
    """OpenAI ChatCompletion을 사용해 질문에 답변합니다. contexts는 리스트(dict)"""
    if not OPENAI_AVAILABLE:
        raise RuntimeError("OpenAI SDK/키가 설정되어 있지 않습니다.")
    # 구성할 컨텍스트 텍스트: 제목, 설명, 댓글(상위 몇개)
    ctx_texts = []
    for ctx in contexts:
        src = ctx.get('source', '')
        txt = ctx.get('text', '')
        ctx_texts.append(f"[{src}] {txt}")
    context_block = "\n\n".join(ctx_texts)[:7000]  # 길이 제한: 안전장치

    system_prompt = (
        "당신은 유튜브 영상 정보를 바탕으로 질문에 답변하는 친절한 도우미입니다. "+
        "아래 제공된 컨텍스트(제목, 설명, 댓글, 또는 Top30 목록)만을 사용하여 사실에 근거한 답변을 작성하세요. "+
        "모를 경우 추측하지 말고 '제공된 정보로는 알기 어렵습니다'라고 답하세요. "+
        "답변은 한국어로 해주세요."
    )
    user_prompt = f"질문: {question}\n\n컨텍스트:\n{context_block}"
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=500,
        )
        answer = resp['choices'][0]['message']['content'].strip()
        return answer
    except Exception as e:
        return f"OpenAI 응답 중 오류가 발생했습니다: {e}"

# 메인 로직: 인기 동영상을 불러오기 및 UI
try:
    trending_videos = get_trending_videos(region_code=region)
    
    if trending_videos:
        st.subheader(f'{region} 지역의 인기 동영상 TOP 30')
        
        # 드롭다운: 영상 선택
        video_options = {f"{i+1}. {v['title']} - {v['channel_title']}": v for i, v in enumerate(trending_videos)}
        selected_label = st.selectbox('영상을 선택하세요 (상세 정보 및 댓글 보기)', list(video_options.keys()))
        selected_video = video_options[selected_label]
        
        # 선택된 영상의 정보 표시
        st.markdown("---")
        st.write(f"### {selected_video['title']}")
        st.write(f"**채널**: {selected_video['channel_title']}")
        st.write(f"**조회수**: {selected_video['view_count']:,}회 | **좋아요**: {selected_video['like_count']:,}개 | **댓글**: {selected_video['comment_count']:,}개")
        if selected_video['thumbnail_url']:
            st.image(selected_video['thumbnail_url'], width=400)
        st.markdown(f"[YouTube에서 보기](https://www.youtube.com/watch?v={selected_video['video_id']})")
        
        # 설명(description) 표시
        with st.expander("📄 영상 설명 보기"):
            desc = selected_video.get('description', '')
            if desc:
                st.text(desc[:1000] + ("..." if len(desc) > 1000 else ""))
            else:
                st.write("설명이 없습니다.")
        
        # 댓글 가져오기
        with st.expander("💬 댓글 보기 (상위 10개)"):
            comments = get_video_comments(selected_video['video_id'], max_results=10)
            if comments:
                for c in comments:
                    st.markdown(f"**{c['author']}** (👍 {c['like_count']})")
                    st.write(c['text'])
                    st.markdown("---")
            else:
                st.write("댓글을 불러올 수 없거나 댓글이 없습니다.")
        
        st.markdown("---")
        
        # 챗봇 섹션
        st.subheader("🤖 영상 챗봇")
        st.write("선택한 영상에 대해 질문하세요. (제목, 설명, 댓글을 바탕으로 답변합니다.)")
        
        user_question = st.text_input("질문을 입력하세요:", key="user_question")
        
        if st.button("질문하기"):
            if not user_question.strip():
                st.warning("질문을 입력해 주세요.")
            else:
                with st.spinner("답변 생성 중..."):
                    # 컨텍스트 구성
                    contexts = []
                    
                    # (옵션) Top30 목록을 컨텍스트에 포함
                    if include_top30_context:
                        top30_lines = []
                        for idx, v in enumerate(trending_videos, start=1):
                            top30_lines.append(f"{idx}. {v['title']} — {v['channel_title']}")
                        top30_text = "\n".join(top30_lines)
                        contexts.append({
                            'source': 'Top30 목록',
                            'text': top30_text
                        })
                    
                    # 선택된 영상 제목
                    contexts.append({
                        'source': '제목',
                        'text': selected_video['title']
                    })
                    
                    # 선택된 영상 설명
                    desc = selected_video.get('description', '')
                    if desc:
                        contexts.append({
                            'source': '설명',
                            'text': desc[:2000]  # 너무 길면 자르기
                        })
                    
                    # 댓글 (상위 몇 개)
                    comments = get_video_comments(selected_video['video_id'], max_results=20)
                    if comments:
                        comment_texts = [f"{c['author']}: {c['text']}" for c in comments[:10]]
                        contexts.append({
                            'source': '댓글',
                            'text': "\n".join(comment_texts)
                        })
                    
                    # 답변 생성
                    if use_openai and OPENAI_AVAILABLE:
                        answer = openai_chat_answer(user_question, contexts)
                    else:
                        answer = keyword_search_answer(user_question, contexts)
                    
                    st.markdown("### 답변:")
                    st.write(answer)
    else:
        st.write('인기 동영상을 불러오지 못했습니다. API 키나 네트워크 연결을 확인해주세요.')

except Exception as e:
    st.error(f"오류 발생: {e}")
    st.write("YouTube API 키가 유효한지, 할당량이 초과되지 않았는지 확인해주세요.")
