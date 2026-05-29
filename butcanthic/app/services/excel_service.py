"""
Excel 数据处理服务
基于 pandas + openpyxl，支持异步加载、Schema提取和安全脚本执行
"""

import asyncio
import base64
import contextlib
import io
import logging
import os
import traceback
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

logger = logging.getLogger(__name__)

_SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
}

_FORBIDDEN_NAMES = {
    "eval", "compile", "exec",
    "breakpoint", "exit", "quit",
}

_FORBIDDEN_MODULES = {
    "os", "sys", "subprocess", "shutil", "pathlib",
    "socket", "http", "urllib", "requests",
    "pickle", "shelve", "marshal", "ctypes",
}


class ExcelDataProcessor:
    """Excel 异步数据处理器"""

    async def load_excel_to_dataframe(
        self,
        file_path: str,
        sheet_name: Optional[str] = None,
        header: int = 0,
    ) -> Dict[str, Any]:
        result = await asyncio.to_thread(
            self._load_sync, file_path, sheet_name, header
        )
        logger.info(
            f"Excel loaded: {file_path}, shape={result['shape']}, "
            f"sheets={result['sheet_names']}"
        )
        return result

    async def extract_excel_schema(
        self,
        file_path: str,
        sheet_name: Optional[str] = None,
        sample_rows: int = 5,
    ) -> Dict[str, Any]:
        """
        提取 Excel 的 Schema 信息，返回 Markdown 和 JSON 格式

        Args:
            file_path: Excel 文件路径
            sheet_name: 工作表名
            sample_rows: 采样行数

        Returns:
            {
                "schema_markdown": str,   # Markdown 格式的 Schema
                "schema_json": dict,      # JSON 结构化 Schema
                "columns": List[str],
                "dtypes": Dict[str, str],
                "null_counts": Dict[str, int],
                "sample_data": List[Dict],
                "shape": tuple,
                "sheet_names": List[str],
                "unique_counts": Dict[str, int],
                "stats": Dict[str, Any],
            }
        """
        result = await asyncio.to_thread(
            self._extract_schema_sync, file_path, sheet_name, sample_rows
        )
        logger.info(
            f"Schema extracted: {file_path}, columns={len(result['columns'])}, "
            f"shape={result['shape']}"
        )
        return result

    async def execute_pandas_code(
        self,
        code: str,
        input_path: str,
        output_path: str,
    ) -> Dict[str, Any]:
        """
        在受限沙盒中执行 LLM 生成的 Pandas 代码

        代码中可使用:
          - df: 已加载的 DataFrame (从 input_path 读取)
          - pd: pandas 库
          - np: numpy 库
          - input_path: 输入文件路径 (str)
          - output_path: 输出文件路径 (str)

        代码需将结果 DataFrame 保存到 output_path

        Args:
            code: LLM 生成的 Python 代码
            input_path: 输入 Excel 路径
            output_path: 输出 Excel 路径

        Returns:
            {
                "success": bool,
                "output_path": Optional[str],
                "error": Optional[str],
                "log": List[str],
                "original_shape": tuple,
                "result_shape": Optional[tuple],
            }
        """
        return await asyncio.to_thread(
            self._execute_pandas_sync, code, input_path, output_path
        )

    async def execute_cleaning_script(
        self,
        df: pd.DataFrame,
        pandas_code_string: str,
    ) -> Dict[str, Any]:
        logs: List[str] = []

        def _print_capture(*args, **kwargs):
            logs.append(" ".join(str(a) for a in args))

        sandbox_globals = {
            "__builtins__": __builtins__,
            **_SAFE_PANDAS,
            "df": df.copy(),
            "np": __import__("numpy"),
            "print": _print_capture,
        }

        try:
            exec(pandas_code_string, sandbox_globals)
            result_df = sandbox_globals.get("df", df)

            if not isinstance(result_df, pd.DataFrame):
                return {
                    "dataframe": df,
                    "shape": df.shape,
                    "success": False,
                    "error": "代码执行后 df 不是 DataFrame 类型",
                    "log": logs,
                }

            logger.info(f"Cleaning script executed: {df.shape} -> {result_df.shape}")
            return {
                "dataframe": result_df,
                "shape": result_df.shape,
                "success": True,
                "error": None,
                "log": logs,
            }

        except Exception as e:
            logger.error(f"Cleaning script failed: {e}")
            return {
                "dataframe": df,
                "shape": df.shape,
                "success": False,
                "error": str(e),
                "log": logs,
            }

    async def execute_python_code(self, file_path: str, code: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self._execute_python_sync, file_path, code)

    async def get_sheet_names(self, file_path: str) -> List[str]:
        return await asyncio.to_thread(self._get_sheets_sync, file_path)

    async def get_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        return {
            "shape": df.shape,
            "columns": df.columns.tolist(),
            "dtypes": {col: str(dt) for col, dt in df.dtypes.items()},
            "null_counts": df.isnull().sum().to_dict(),
            "numeric_summary": df.describe().to_dict() if df.select_dtypes(include="number").shape[1] > 0 else {},
        }

    def _load_dataframe(self, file_path: str):
        if file_path.lower().endswith('.csv'):
            try:
                return pd.read_csv(file_path)
            except UnicodeDecodeError:
                return pd.read_csv(file_path, encoding='gbk')
        else:
            return pd.read_excel(file_path)

    def _extract_schema_sync(
        self,
        file_path: str,
        sheet_name: Optional[str],
        sample_rows: int,
    ) -> Dict[str, Any]:
        if file_path.lower().endswith('.csv'):
            sheet_names = ["Sheet1"]
            target = "Sheet1"
            df = self._load_dataframe(file_path)
        else:
            xl = pd.ExcelFile(file_path, engine="openpyxl")
            sheet_names = xl.sheet_names
            target = sheet_name or sheet_names[0]
            df = pd.read_excel(xl, sheet_name=target)

        columns = df.columns.tolist()
        dtypes = {col: str(dt) for col, dt in df.dtypes.items()}
        null_counts = df.isnull().sum().to_dict()
        unique_counts = {col: int(df[col].nunique()) for col in columns}
        sample = df.head(sample_rows)

        schema_json = {
            "file": os.path.basename(file_path),
            "sheet": target,
            "shape": list(df.shape),
            "columns": [],
        }
        for col in columns:
            schema_json["columns"].append({
                "name": col,
                "dtype": dtypes[col],
                "null_count": int(null_counts.get(col, 0)),
                "unique_count": unique_counts.get(col, 0),
                "sample_values": _safe_values(df[col].head(sample_rows)),
            })

        md_lines = [
            f"## File: {os.path.basename(file_path)} (Sheet: {target})",
            f"**Shape**: {df.shape[0]} rows × {df.shape[1]} columns",
            "",
            "| # | Column | Type | Nulls | Unique | Sample Values |",
            "|---|--------|------|-------|--------|---------------|",
        ]
        for i, col in enumerate(columns):
            samples = ", ".join(str(v) for v in _safe_values(df[col].head(3)))
            md_lines.append(
                f"| {i+1} | {col} | {dtypes[col]} | {null_counts.get(col, 0)} | "
                f"{unique_counts.get(col, 0)} | {samples} |"
            )

        md_lines.append("")
        md_lines.append("### Sample Data (first {} rows)".format(min(sample_rows, len(df))))
        md_lines.append(sample.to_markdown(index=False))

        stats = {}
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        if numeric_cols:
            desc = df[numeric_cols].describe()
            for col in numeric_cols:
                stats[col] = {
                    "mean": _safe_float(desc.loc["mean", col]) if "mean" in desc.index else None,
                    "std": _safe_float(desc.loc["std", col]) if "std" in desc.index else None,
                    "min": _safe_float(desc.loc["min", col]) if "min" in desc.index else None,
                    "max": _safe_float(desc.loc["max", col]) if "max" in desc.index else None,
                }

        return {
            "schema_markdown": "\n".join(md_lines),
            "schema_json": schema_json,
            "columns": columns,
            "dtypes": dtypes,
            "null_counts": null_counts,
            "unique_counts": unique_counts,
            "sample_data": sample.to_dict(orient="records"),
            "shape": df.shape,
            "sheet_names": sheet_names,
            "stats": stats,
        }

    def _execute_python_sync(self, file_path: str, code: str) -> Dict[str, Any]:
        try:
            df = self._load_dataframe(file_path)
        except Exception as e:
            return {"success": False, "error": f"Failed to read file: {e}", "output": "", "image_base64": None}

        local_vars = {"df": df, "plt": plt, "pd": pd}
        sandbox_globals = {
            "__builtins__": __builtins__,
            "pd": pd,
            "plt": plt,
            "df": df,
        }
        output_capture = io.StringIO()

        try:
            with contextlib.redirect_stdout(output_capture):
                exec(code, sandbox_globals)

            output = output_capture.getvalue()

            img_base64 = None
            if plt.get_fignums():
                img_buf = io.BytesIO()
                plt.savefig(img_buf, format='png', bbox_inches='tight', dpi=150)
                img_buf.seek(0)
                img_base64 = base64.b64encode(img_buf.read()).decode('utf-8')
                plt.close('all')

            return {"success": True, "output": output, "image_base64": img_base64}

        except Exception:
            err_msg = traceback.format_exc()
            plt.close('all')
            return {"success": False, "error": err_msg, "output": "", "image_base64": None}

    def _execute_pandas_sync(
        self,
        code: str,
        input_path: str,
        output_path: str,
    ) -> Dict[str, Any]:
        logs: List[str] = []

        def _print_capture(*args, **kwargs):
            logs.append(" ".join(str(a) for a in args))

        _code_check = _check_code_safety(code)
        if _code_check:
            return {
                "success": False,
                "output_path": None,
                "error": _code_check,
                "log": logs,
                "original_shape": None,
                "result_shape": None,
            }

        try:
            df = self._load_dataframe(input_path)
            original_shape = df.shape
            logger.info(f"Sandbox: loaded {input_path}, shape={original_shape}")
        except Exception as e:
            return {
                "success": False,
                "output_path": None,
                "error": f"Failed to read input file: {e}",
                "log": logs,
                "original_shape": None,
                "result_shape": None,
            }

        import numpy as np

        sandbox_globals = {
            "__builtins__": __builtins__,
            **_SAFE_PANDAS,
            "np": np,
            "df": df,
            "input_path": input_path,
            "output_path": output_path,
            "print": _print_capture,
        }

        try:
            exec(code, sandbox_globals)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Sandbox exec failed: {e}\n{tb}")
            return {
                "success": False,
                "output_path": None,
                "error": f"{type(e).__name__}: {e}",
                "log": logs,
                "original_shape": original_shape,
                "result_shape": None,
            }

        result_df = sandbox_globals.get("df")
        if result_df is not None and isinstance(result_df, pd.DataFrame):
            try:
                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                result_df.to_excel(output_path, index=False, engine="openpyxl")
                logger.info(f"Sandbox: saved result to {output_path}, shape={result_df.shape}")
            except Exception as e:
                return {
                    "success": False,
                    "output_path": None,
                    "error": f"Failed to save output: {e}",
                    "log": logs,
                    "original_shape": original_shape,
                    "result_shape": list(result_df.shape) if isinstance(result_df, pd.DataFrame) else None,
                }
        else:
            if os.path.exists(output_path):
                logger.info(f"Sandbox: code saved output via output_path variable")
            else:
                return {
                    "success": False,
                    "output_path": None,
                    "error": "Code did not produce a valid DataFrame (df) or save to output_path",
                    "log": logs,
                    "original_shape": original_shape,
                    "result_shape": None,
                }

        result_shape = None
        if isinstance(result_df, pd.DataFrame):
            result_shape = list(result_df.shape)

        return {
            "success": True,
            "output_path": output_path,
            "error": None,
            "log": logs,
            "original_shape": original_shape,
            "result_shape": result_shape,
        }

    def _load_sync(
        self, file_path: str, sheet_name: Optional[str], header: int
    ) -> Dict[str, Any]:
        if file_path.lower().endswith('.csv'):
            sheet_names = ["Sheet1"]
            df = self._load_dataframe(file_path)
        else:
            xl = pd.ExcelFile(file_path, engine="openpyxl")
            sheet_names = xl.sheet_names
            target = sheet_name or sheet_names[0]
            df = pd.read_excel(xl, sheet_name=target, header=header)
        preview = df.head(20).to_dict(orient="records")
        return {
            "dataframe": df,
            "shape": df.shape,
            "columns": df.columns.tolist(),
            "dtypes": {col: str(dt) for col, dt in df.dtypes.items()},
            "sheet_names": sheet_names,
            "null_counts": df.isnull().sum().to_dict(),
            "preview": preview,
        }

    def _get_sheets_sync(self, file_path: str) -> List[str]:
        if file_path.lower().endswith('.csv'):
            return ["Sheet1"]
        xl = pd.ExcelFile(file_path, engine="openpyxl")
        return xl.sheet_names


_SAFE_PANDAS = {
    "pd": pd,
    "DataFrame": pd.DataFrame,
    "Series": pd.Series,
    "NA": pd.NA,
    "Timestamp": pd.Timestamp,
    "Timedelta": pd.Timedelta,
    "to_datetime": pd.to_datetime,
    "to_numeric": pd.to_numeric,
    "concat": pd.concat,
    "merge": pd.merge,
    "melt": pd.melt,
    "pivot_table": pd.pivot_table,
    "cut": pd.cut,
    "qcut": pd.qcut,
}


def _safe_values(series: pd.Series) -> list:
    result = []
    for v in series:
        if pd.isna(v):
            result.append("NaN")
        else:
            result.append(str(v))
    return result


def _safe_float(val) -> Optional[float]:
    try:
        if pd.isna(val):
            return None
        return round(float(val), 4)
    except (ValueError, TypeError):
        return None


def _check_code_safety(code: str) -> Optional[str]:
    stripped_lines = []
    for line in code.split("\n"):
        s = line.strip()
        if s and not s.startswith("#"):
            stripped_lines.append(s)

    for line in stripped_lines:
        tokens = line.split()
        if not tokens:
            continue

        first = tokens[0]
        if first == "import" and len(tokens) >= 2:
            module = tokens[1].split(".")[0]
            if module in _FORBIDDEN_MODULES:
                return f"Forbidden import: {module}"
        if first == "from" and len(tokens) >= 2:
            module = tokens[1].split(".")[0]
            if module in _FORBIDDEN_MODULES:
                return f"Forbidden import from: {module}"

        for name in _FORBIDDEN_NAMES:
            if f" {name}(" in line or line.startswith(f"{name}("):
                return f"Forbidden function: {name}"

    return None
