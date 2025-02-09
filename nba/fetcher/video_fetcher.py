from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from functools import lru_cache
from config.nba_config import NBAConfig
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig


@dataclass
class VideoRequestConfig(BaseRequestConfig):
    """视频请求配置"""
    BASE_URL: str = "https://stats.nba.com/stats"
    CACHE_PATH: Path = field(default_factory=lambda: Path(str(NBAConfig.PATHS.VIDEOURL_CACHE_DIR)))
    CACHE_DURATION: timedelta = field(default_factory=lambda: timedelta(seconds=3600))
    FALLBACK_URLS: Dict[str, str] = field(
        default_factory=lambda: {
            "https://cdn.nba.com/static/json": "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/NBA",
        }
    )

    def __post_init__(self):
        """配置后处理：验证并转换类型"""
        # 确保 CACHE_PATH 是 Path 对象
        if not isinstance(self.CACHE_PATH, Path):
            self.CACHE_PATH = Path(str(self.CACHE_PATH))

        # 确保缓存目录存在
        self.CACHE_PATH.mkdir(parents=True, exist_ok=True)

        if not isinstance(self.CACHE_DURATION, timedelta):
            raise ValueError("CACHE_DURATION must be a timedelta instance")


class ContextMeasure(str, Enum):
    """视频查询的上下文度量类型"""
    FG3M = "FG3M"  # 三分命中
    FG3A = "FG3A"  # 三分出手
    FGM = "FGM"  # 投篮命中
    FGA = "FGA"  # 投篮出手
    OREB = "OREB"  # 进攻篮板
    DREB = "DREB"  # 防守篮板
    REB = "REB"  # 总篮板
    AST = "AST"  # 助攻
    STL = "STL"  # 抢断
    BLK = "BLK"  # 盖帽
    TOV = "TOV"  # 失误


@dataclass
class VideoRequestParams:
    """视频查询参数构建器"""
    game_id: str
    player_id: Optional[str] = None
    team_id: Optional[str] = None
    context_measure: ContextMeasure = ContextMeasure.FGM
    season: str = "2024-25"
    season_type: str = "Regular Season"

    def build(self) -> dict:
        """构建与NBA API完全一致的查询参数"""
        return {
            'LeagueID': "00",
            'Season': self.season,
            'SeasonType': self.season_type,
            'TeamID': int(self.team_id) if self.team_id else 0,
            'PlayerID': int(self.player_id) if self.player_id else 0,
            'GameID': self.game_id,
            'ContextMeasure': self.context_measure.value,
            'Outcome': '',
            'Location': '',
            'Month': 0,
            'SeasonSegment': '',
            'DateFrom': '',
            'DateTo': '',
            'OpponentTeamID': 0,
            'VsConference': '',
            'VsDivision': '',
            'Position': '',
            'RookieYear': '',
            'GameSegment': '',
            'Period': 0,
            'LastNGames': 0,
            'ClutchTime': '',
            'AheadBehind': '',
            'PointDiff': '',
            'RangeType': 0,
            'StartPeriod': 0,
            'EndPeriod': 0,
            'StartRange': 0,
            'EndRange': 28800,
            'ContextFilter': '',
            'OppPlayerID': ''
        }


class VideoFetcher(BaseNBAFetcher):
    """视频链接数据获取器"""
    request_config = VideoRequestConfig()
    VIDEO_STATS_URL = "https://stats.nba.com/stats/videodetailsasset"

    def __init__(self):
        super().__init__()
        self.http_manager.headers.update({
            'accept': '*/*',
            'accept-language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
            'accept-encoding': 'gzip, deflate, br, zstd',
            'connection': 'keep-alive',
            'dnt': '1',
            'host': 'stats.nba.com',
            'origin': 'https://www.nba.com',
            'referer': 'https://www.nba.com/',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0'
        })

    @lru_cache(maxsize=100)
    def get_game_videos_raw(self, game_id: str, context_measure: ContextMeasure = ContextMeasure.FGM,
                            player_id: Optional[int] = None, team_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """获取比赛视频数据"""
        try:
            # 构建和验证请求参数
            params = VideoRequestParams(
                game_id=game_id,
                player_id=str(player_id) if player_id else None,
                team_id=str(team_id) if team_id else None,
                context_measure=context_measure
            ).build()

            # 构建缓存键
            cache_key_parts = list(filter(None, [
                'video',
                game_id,
                str(player_id) if player_id else None,
                str(team_id) if team_id else None,
                context_measure.value
            ]))

            # 确保缓存文件路径存在
            cache_file = self.request_config.CACHE_PATH / 'videos_url.json'
            cache_file.parent.mkdir(parents=True, exist_ok=True)

            # 缓存配置
            cache_config = {
                'key': '_'.join(cache_key_parts),
                'file': cache_file,  # 转换为字符串以确保兼容性
                'interval': int(self.request_config.CACHE_DURATION.total_seconds()),
                'force_update': False
            }

            # 发起请求并处理响应
            return self.fetch_data(
                url=self.VIDEO_STATS_URL,
                params=params,
                cache_config=cache_config
            )

        except Exception as e:
            self.logger.error(f"获取视频数据失败: {e}", exc_info=True)
            return None