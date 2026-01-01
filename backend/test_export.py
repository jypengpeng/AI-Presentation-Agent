"""Quick test script for ZIP export."""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

async def test_zip_export():
    from export.zip_exporter import ZipExporter
    from config import get_settings
    
    # 使用实际的 workspace 路径
    workspace = Path("D:/tool/auto_presentation_refactor_version/data/tasks/task_496d6d15/workspace")
    
    print(f"Testing export with workspace: {workspace}")
    print(f"Slides path exists: {(workspace / 'slides').exists()}")
    print(f"Screenshots path exists: {(workspace / 'screenshots').exists()}")
    
    settings = get_settings()
    exporter = ZipExporter(workspace, settings=settings)
    
    # 导出 ZIP（不包含演讲稿，加快测试速度）
    output_path = workspace / "test_export.zip"
    
    print("\nStarting export...")
    result = await exporter.export_async(
        output_path=output_path,
        include_pptx=True,
        include_speech=False,  # 跳过演讲稿生成
        include_screenshots=True,
        return_bytes=False
    )
    
    print(f"\nExport completed: {result}")
    
    # 显示 ZIP 内容
    import zipfile
    if isinstance(result, Path) and result.exists():
        with zipfile.ZipFile(str(result), 'r') as zf:
            print("\nZIP contents:")
            for name in zf.namelist():
                info = zf.getinfo(name)
                print(f"  {name} ({info.file_size} bytes)")
    else:
        print(f"Result type: {type(result)}")

if __name__ == "__main__":
    asyncio.run(test_zip_export())