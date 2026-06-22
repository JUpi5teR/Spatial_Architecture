Project Architecture Upgrade: Convert into Notebook-based Workspace

基于当前已有项目进行 架构升级，不是重构已有功能。

目标：

将整个系统改造成类似 NotebookLM + CVAT 的结构：

顶层为 Homepage（Notebook 管理层）
每个 Notebook 是独立工作空间（Workspace）
原本所有功能（Upload Data / Clustering / Statistics / Plots / Heatmap）都移动到 Notebook 内部

原则：

保持已有功能逻辑不变
改变整体组织结构
增加数据库持久化
1. Global Structure Upgrade

原结构：

App
├── Upload Data
├── Clustering
├── Statistics
├── Plots
├── Heatmap

升级为：

App
├── Homepage
│   ├── Notebook List
│   ├── Database Panel
│   ├── Create Notebook
│   └── Trash
│
└── Notebook Workspace
    ├── Upload Data
    ├── Clustering
    ├── Statistics
    ├── Plots
    └── Heatmap
2. Homepage（新的根页面）

Homepage 作为入口页面。

特点：

没有左侧 sidebar
展示所有 Notebook 记录
类似 NotebookLM 的 notebook 卡片布局

展示内容：

每个 Notebook 卡片：

notebook name
create time
last modified time
dataset count
preview image（如果存在）

支持：

点击进入 notebook
重命名 notebook
删除 notebook（进入 Trash）

新增：

Create Notebook Button

功能：

新建 notebook：

默认：

Notebook_{timestamp}

创建后：

自动进入 notebook 内部：

default page = Upload Data
3. Notebook Workspace（原功能整体迁移）

原有：

Upload Data
Clustering
Statistics
Plots
Heatmap

全部作为 notebook 内部功能。

现在逻辑变为：

Homepage
   ↓
Notebook
   ↓
Upload Data
   ↓
Clustering
   ↓
Statistics
   ↓
Plots

Upload Data
   ↓
Heatmap

新增：

点击：

Homepage

返回：

Homepage notebook list
4. Upload Data（改为 notebook scoped）

现在每个 notebook 拥有独立 data。

即：

原来：

global app data

改为：

notebook-local data

每个 notebook 的上传数据绑定到 notebook id。

要求：

支持：

folder upload
zip upload
auto unzip

保留：

File Structure Guide

上传后：

写入数据库。

5. Database System（新增核心模块）

新增独立 Database 页面（在 Homepage 内展示）。

数据库使用：

PostgreSQL

用途：

记录所有 notebook 和 notebook 中的数据上传记录。

数据库设计：

Table: notebooks
id
name
created_at
updated_at
status
deleted_at
Table: datasets
id
notebook_id
name
upload_time
file_path
preview_image
ground_truth_path
results_path
train_log_path
status

默认：

name = upload_timestamp
6. Database Panel（Homepage 中展示）

新增 Database 面板。

功能：

展示所有上传记录（datasets）：

内容：

dataset name
notebook name
upload time
file path

支持：

Select dataset

功能：

点击后：

加载该 dataset
打开所属 notebook
展示内容

支持：

CRUD

数据库中的 data 可：

Create（上传新增）
Read（查看）
Update（重命名/替换）
Delete（删除）

注意：

这里操作的是：

upload record

不是原始文件本身。

7. Trash System

Homepage 左下角固定：

Trash icon

功能：

回收：

deleted notebooks

行为：

删除 notebook：

不是立即删除：

move to trash

Trash 支持：

restore
permanent delete

数据库中：

deleted_at != NULL

表示已删除。

8. Notebook Empty State

新建 notebook 后：

默认进入：

Upload Data

如果没有上传数据：

以下页面全部不可用：

Clustering
Statistics
Plots
Heatmap

显示：

No dataset loaded.
Please upload data first.

逻辑：

Notebook created
   ↓
Upload Data required
   ↓
Other modules unlocked
9. Data Binding Rules（重要）

现在数据绑定关系：

Notebook
   ↓
Dataset
   ↓
Ground Truth
   ↓
Results
   ↓
Train Log

即：

一个 notebook 可以拥有多个 dataset。

切换 dataset：

动态刷新：

Clustering
Statistics
Plots
Heatmap
10. Important Constraints

这是增量升级：

禁止：

重写已有 Clustering
重写已有 Statistics
重写已有 Plots
重写已有 Heatmap

只允许：

把它们迁移到 notebook 内部
增加 Homepage 层
增加 PostgreSQL 数据持久层
增加 notebook 管理逻辑
增加 dataset 管理逻辑
增加 Trash 逻辑

核心目标：

实现：

Notebook-centric workspace
Dataset persistence
Database-backed records
Multi-notebook management
Trash recovery system