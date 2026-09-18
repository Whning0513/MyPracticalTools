# artifactManifest

`artifact-manifest` 为目录生成一个小而确定的 JSON 文件清单，并在复制、上传或交接之后核对它。

清单记录相对路径、字节数、SHA-256 和简单的媒体类型。条目按路径排序；清单放在目录内部时不会把自己算进去。符号链接会直接报错，不会被跟随到目录之外。

## 快速开始

```bash
python -m pip install -e '.[test]'
artifact-manifest create ./artifact ./artifact.manifest.json --exclude '*.tmp'
artifact-manifest verify ./artifact ./artifact.manifest.json --exclude '*.tmp'
```

目录完全一致时退出码为 `0`；发现缺失、修改或多出的文件时为 `1`；输入或清单格式有问题时为 `2`。

格式保持为普通 JSON，方便审阅、归档，也方便其他工具读取。
