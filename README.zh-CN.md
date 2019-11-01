# thunderbird-website

这个库包含着 Thunderbird客户端中起始页 和 [www.thunderbird.net](https://www.thunderbird.net/) 网站。
*  `prod`分支 曾经用于更新[start.thunderbird.net](https://start.thunderbird.net/)和 [www.thunderbird.net](https://www.thunderbird.net/)。
*  `master` 分支 曾经用于更新 [start-stage](https://start-stage.thunderbird.net) 和[stage](https://www-stage.thunderbird.net.)

# 搭建说明
## 依赖
在 Ubuntu， 您将需要使用apt-get而不是yum，并且对于不同的程序包管理器也类似。
此外，该网站与LESS 3.0或更高版本不兼容。
```
pip install -r requirements.txt
git clone https://github.com/thundernest/thunderbird-notes.git thunderbird_notes
git clone https://github.com/mozilla/product-details-json
sudo yum install npm
sudo npm install -g less@2.7.2
```

如果您需要本地化以显示从英语翻译成其他语言的页面：

```
git clone https://github.com/thundernest/thunderbird.net-l10n.git locale
l10n_tools/compile.sh
```

##运行搭建

一个基本的搭建是`python build-site.py`.
它默认将 搭建[www.thunderbird.net](https://www.thunderbird.net/) 进 `thunderbird.net` 目录
还有其他参数：

* `--startpage`
    *这个将把 [start page](https://start.thunderbird.net/) 搭建进 `site`目录。
* `--enus`
    * 这将构建限制为仅在“ en-US”区域设置，以便进行更快的测试。
* `--debug`
    * 该日志记录了所构建的每个语言环境和某些模板的输出，用于简化调试。
* `--watch`
    * 这将在本地主机端口8000上启动HTTP服务器，并监视模板和资源文件夹中的更改，然后进行快速重建。
    * 请注意，这仅在您修改文件时重建。 要添加或删除文件，您应该开始一个新的版本。
* `--port`
    * 设置用于本地主机服务器的端口。 默认值为8000。格式： `--port 8000`.

* thunderbird.net 模板 位于 `website`目录中，起始页面位于`start-page` 目录中.  资源是共享的并在 `assets`目录中。
## 查看网站
要查看网站以进行测试， 运行 `python build-site.py --watch`。 这也适用于起始页。
然后，您可以导航到：http://127.0.0.1:8000以查看该网站。 没有任何apache重定向在此模式下有效，因此您必须点击在浏览器中手动设置所需的语言环境，但此后该站点应正常运行。


## 自动化构建
通常，您只需要手动构建网站即可进行测试和开发。 每个存储库上的Webhook触发，在以下情况下自动重建：

* [thunderbird-notes](https://github.com/thundernest/thunderbird-notes.git) (发行说明) 被更新。
* [product-details](https://github.com/mozilla/product-details-json) (产品细节) 被更新。产品详细信息包含有关存在哪些Thunderbird版本的数据。
    * 当前阶段不会根据产品详细信息更改自动更新。
这两个更新频率都足够高（每周多次），因此不需要独立进行本地化更新。 任何触发
更新将始终使用所有来源的最新数据。 如果对上述存储库之一的更改在生成的文件中未产生任何更改，则不会
Web服务器的更新将发生。

# 手动网站更新
有时您需要手动更新站点，例如将对此仓库所做的更改移至阶段和生产，或者因为自动化
失败或类似原因。 您需要按照https://github.com/thundernest/thundernest-ansible文档中的说明登录到控制节点
或签出并在本地计算机上设置最迅捷的脚本。 有关该文档的内容，见
[thundernest-ansible](https://github.com/thundernest/thundernest-ansible).
假设您已登录到控制节点或设置了最迅捷的功能：

对于当前阶段：

```
cd thundernest-ansible
source files/secrets.sh
ansible-playbook plays/website-build.yml
```

对于产品:
```
cd thundernest-ansible
source files/secrets.sh
ansible-playbook --extra-vars="branch=prod" plays/website-build.yml
```

这个[website-build.yml](https://github.com/thundernest/thundernest-ansible/blob/master/plays/website-build.yml) ansible脚本执行网站的完整构建，包括启动
页面和thunderbird.net本身。

* 通过自动化构建或 [website-build.yml](https://github.com/thundernest/thundernest-ansible/blob/master/plays/website-build.yml) 脚本被检入https://github.com/thundernest/tb-website-builds -- 这个 `master`分支代表当前阶段中的文件，并且  `prod` 分支表示当前在线版本的thunderbird.net上的文件。
