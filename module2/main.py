"""
模块2主程序入口
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from module2.model_evaluation import main

if __name__ == "__main__":
    main()

