# 工具说明（`_tools\`）

> 这些是知识库的自动化工具。**平时你不用手动跑** —— 跟 AI 说一声，它自己会调用。
> 本目录工具**不依赖任何第三方包**（除 PDF 抽取需要 `pymupdf`、`.doc` 抽取需要本机 Word）。

---

## 一、抽取：把文件变成文字

| 工具 | 干什么 | 依赖 |
|---|---|---|
| `kb_extract.py` | **统一入口**。`python kb_extract.py <源文件> <输出md>` | — |
| `extract_pdf.py` | PDF 抽取 + 元信息识别（年份/类型/学位代码等） | Python + pymupdf |
| `extract_word.ps1` | `.doc` / `.docx` 抽取 | **本机 Word**（Office） |
| `extract_office.py` | `.pptx` / `.xlsx` / `.txt` / `.md` / `.html` / `.csv` | 无（只用标准库） |

## 二、归档：把文件正式收进库

| 工具 | 干什么 |
|---|---|
| `kb_import.py` | **标准入口**。`python kb_import.py --cat <分类> [--dry-run] <文件...>` |
| `kb_cats.py` | 各分类的编号规则与元信息提取（被 `kb_import.py` 调用，不单独跑） |
| `kb_import_stage1.py` | 两阶段导入·第一步：**非提权**环境下抽取并定编号，结果写 JSON |
| `kb_import_stage2.py` | 两阶段导入·第二步：**提权**环境下纯文件落盘（见第五节） |

## 三、索引与检查

| 工具 | 干什么 |
|---|---|
| `kb_rebuild_index.py` | **从卡片重建 INDEX / TAGS**。卡片是唯一真源，索引只是派生视图 |
| `verify.py` | 体检 |
| `meta_regression.py` | 元信息回归探针：改过抽取逻辑后跑一遍，确认老文件结果没变 |

## 四、素材筛选（一次性用的，留档）

| 工具 | 干什么 |
|---|---|
| `scan_meta.py` | 批量扫描素材目录，输出清单 TSV（年份/代码/标题/……） |
| `pick_candidates.py` | 从清单里按关键词筛出目标学科候选 |
| `word_scan.ps1` / `word_scan2.ps1` | 早期批量扫描脚本，**已被直接循环调用取代**，仅留档 |

## 五、什么时候需要「两阶段导入」

正常情况下用 `kb_import.py` 就够了。

**但如果 AI 是在受限沙箱里干活**（比如 DSH 的 harness），会遇到一个坑：

> **提权写库时 Word COM 会挂死**（非提权只要 5 秒）。

这时改用两阶段：

```
# 第一步（不提权）：抽取 + 查重 + 定编号，结果写入 JSON
python _tools\kb_import_stage1.py <分类> <临时json> <文件...>

# 第二步（提权）：纯文件 I/O —— 复制原件、写 md、更新 hashes/manifest/INDEX
python _tools\kb_import_stage2.py <临时json>
```

## 六、写工具时的几个坑（本机实测）

- **中文输出到 PowerShell 控制台容易乱码** → 结果一律写 UTF-8 文件，再用编辑器/读取工具看
- 脚本**控制台只打印 ASCII**，中文走文件或 JSON 的 `\uXXXX` 转义
- **`.doc` 抽取依赖本机 Word**：换电脑必须装 Office，否则这一类会失败
- **`.doc` 写出来的是 GB18030**，要按代码页 54936 解码，否则乱码
- 老 `.ppt` / `.xls`（OLE2 复合文档）**本库不处理**，会提示"请先另存为新格式"
- 抽取长度有 **30 万字符上限**（超出截断并提示），避免生成 AI 读不动的巨型 md
