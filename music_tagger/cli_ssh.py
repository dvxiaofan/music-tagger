"""SSH-compatible CLI for remote execution"""

import sys
sys.path.insert(0, '/vol2/1000/openclaw/music-tagger')

from music_tagger.config import Config
from music_tagger.pipeline import Pipeline

def main():
    config = Config('/vol2/1000/openclaw/music-tagger/config-nas.yaml')
    pipeline = Pipeline(config)
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
    else:
        command = 'status'
    
    try:
        if command == 'status':
            stats = pipeline.status()
            print('=== 音乐标签处理状态 ===')
            for key, value in stats.items():
                print(f'  {key}: {value}')
            print(f'  合计: {sum(stats.values())}')
        elif command == 'run':
            print('开始执行完整流程...')
            pipeline.run()
            stats = pipeline.status()
            print('=== 执行完成 ===')
            for key, value in stats.items():
                print(f'  {key}: {value}')
            print(f'  合计: {sum(stats.values())}')
        else:
            print(f'未知命令: {command}')
    except Exception as e:
        print(f'错误: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        pipeline.close()

if __name__ == '__main__':
    main()
