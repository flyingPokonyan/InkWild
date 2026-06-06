# IP Anchor 可行性实验

> 跑于 2026-05-25 17:17，单次 LLM 调用（_pre_extract_canon 等价），无 Tavily grounding。
> 目标：验证 LLM 能否稳定写出 L1/L3 plot anchors，决定 spec B 块走 anchor 路线还是预定义字典路线。

## TL;DR

- **福尔摩斯** — parse_ok=True | anchors=6 | verdict=**USABLE** | good=6 bad=0 | with_forbidden_alt=6 | 55.1s | raw=5287字
- **狄仁杰（神探狄仁杰系列）** — parse_ok=True | anchors=6 | verdict=**USABLE** | good=6 bad=0 | with_forbidden_alt=6 | 85.8s | raw=5244字

---

## 福尔摩斯 (novel)

- elapsed: 55.1s | raw_chars: 5287 | parse_ok: True
- 总 anchors: 6 / 带 forbidden_alternatives: 6
- 启发式判定: **USABLE**

### inviolable_plot_anchors

**1.** kind=`relation` subjects=`['夏洛克·福尔摩斯', '约翰·华生']`
   - statement: 福尔摩斯与华生是终生挚友与传奇搭档，彼此绝对信任，且华生是福尔摩斯唯一真正认可的情感依靠与传记书写者。
   - forbidden: 将两人塑造成相互猜忌或背叛的关系
   - forbidden: 设定两人因利益或爱情而决裂

**2.** kind=`relation` subjects=`['夏洛克·福尔摩斯', '詹姆斯·莫里亚蒂']`
   - statement: 福尔摩斯与莫里亚蒂是智力与道德上的终极宿敌，彼此视对方为必须摧毁的对手，且莫里亚蒂是福尔摩斯冒险生涯的顶峰挑战。
   - forbidden: 将莫里亚蒂设定为福尔摩斯的秘密导师或另有隐情的伙伴
   - forbidden: 淡化两人的对立，改为普通犯罪者报复

**3.** kind=`identity` subjects=`['艾琳·艾德勒']`
   - statement: 艾琳·艾德勒是唯一在智力对决中正面挫败福尔摩斯的女性，并在福尔摩斯心中拥有特殊地位，但并非他的浪漫恋人。
   - forbidden: 将艾琳·艾德勒设定为福尔摩斯的长期秘密情人或夫妻
   - forbidden: 改变她作为聪明独立歌剧演员的核心身份，降格为被拯救的受害者

**4.** kind=`outcome` subjects=`['莱辛巴赫瀑布事件']`
   - statement: 在莱辛巴赫瀑布，福尔摩斯与莫里亚蒂发生搏斗，最终莫里亚蒂坠崖身亡，福尔摩斯假死隐匿，此事件是两人关系的终点。
   - forbidden: 让莫里亚蒂生还并继续在幕后操控
   - forbidden: 将福尔摩斯的假死改为真的死亡，且无归来

**5.** kind=`identity` subjects=`['夏洛克·福尔摩斯', '可卡因使用']`
   - statement: 福尔摩斯在无案时用可卡因进行7%溶液注射以对抗无聊，这是他性格中阴暗面的标志，代表天才对刺激的依赖。
   - forbidden: 将福尔摩斯描绘为完全无瘾的正面楷模，删除这一设定
   - forbidden: 将他刻画成重度毒瘾者而丧失推理能力

**6.** kind=`relation` subjects=`['福尔摩斯', '麦克罗夫特·福尔摩斯']`
   - statement: 麦克罗夫特是夏洛克·福尔摩斯的哥哥，拥有更杰出的推理天赋但极度懒惰，是英国政府的关键智囊，两人保持疏远但互相尊重的关系。
   - forbidden: 将麦克罗夫特设定为敌对关系或平庸之人
   - forbidden: 让麦克罗夫特成为犯罪幕后黑手

### forbidden_name_patterns

- 禁止使用现代风格的英文名缩写如“Sherlock H.”或音译变体如“歇洛克·福”，必须保持原著全称“夏洛克·福尔摩斯”或“Sherlock Holmes”的完整语法。
- 禁止给贝克街221B房东杜撰中文姓式如“黄太太”或“李婶”，必须保留哈德森太太这一原名音译，以防破坏维多利亚英伦氛围。
- 禁止为原作已有的角色创造昵称如“老福”“小莫”，必须使用正式称呼或原著中出现的称谓。

### 关键人物（前 8 个）

- **夏洛克·福尔摩斯** (第一主角，顾问侦探, must_have=True) — 关系: 本人
- **约翰·H·华生** (第一人称叙述者，福尔摩斯的助手与挚友, must_have=True) — 关系: 室友、传记作者、生死之交
- **詹姆斯·莫里亚蒂教授** (首要反派，犯罪界的拿破仑, must_have=True) — 关系: 宿敌，智力与势力的终极对立者
- **哈德森太太** (贝克街221B的房东，日常照料者, must_have=False) — 关系: 房东与几乎家人的关系
- **雷斯垂德探长** (苏格兰场警官，经常求助福尔摩斯, must_have=False) — 关系: 专业上的合作者与偶尔的竞争者
- **艾琳·艾德勒** (唯一击败过福尔摩斯的女性，女高音歌唱家, must_have=False) — 关系: 智力上的对手与尊敬的对象，福尔摩斯口中的“那个女人”

---

## 狄仁杰（神探狄仁杰系列） (tv)

- elapsed: 85.8s | raw_chars: 5244 | parse_ok: True
- 总 anchors: 6 / 带 forbidden_alternatives: 6
- 启发式判定: **USABLE**

### inviolable_plot_anchors

**1.** kind=`relation` subjects=`['狄仁杰', '李元芳']`
   - statement: 李元芳是狄仁杰的贴身护卫与义子般的存在，二人之间有着牢不可破的忠诚与信任。
   - forbidden: 李元芳被改成蛇灵卧底，最终背叛并率众围攻狄仁杰。
   - forbidden: 二人因误解反目成仇，李元芳自立门户对抗狄仁杰。

**2.** kind=`identity` subjects=`['肖清芳']`
   - statement: 肖清芳是蛇灵组织的实际领导者（大姐），主导了对朝廷的一系列阴谋。
   - forbidden: 肖清芳被洗白为被袁天罡胁迫的受害者，其所有罪行都是被逼无奈。
   - forbidden: 肖清芳其实是朝廷派入蛇灵的卧底，所做一切皆为配合狄仁杰的布局。

**3.** kind=`outcome` subjects=`['如燕', '蛇灵']`
   - statement: 如燕在蛇灵案中彻底脱离蛇灵控制，并被狄仁杰收为义女。
   - forbidden: 如燕在最后一刻选择回归蛇灵，并刺杀狄仁杰或李元芳。
   - forbidden: 如燕的真实身份依然是蛇灵卧底，潜伏在狄仁杰身边传递假情报。

**4.** kind=`relation` subjects=`['如燕', '李元芳']`
   - statement: 如燕与李元芳是生死与共的恋人，最终走到一起。
   - forbidden: 如燕移情别恋他人，或为蛇灵任务与虺文忠、虎敬晖等发展感情线。
   - forbidden: 李元芳与如燕的感情被改写为兄妹情，或完全删除此感情线。

**5.** kind=`outcome` subjects=`['狄仁杰', '武则天']`
   - statement: 狄仁杰终生未反叛武则天，武则天也始终未因猜忌而诛杀狄仁杰。
   - forbidden: 狄仁杰最终加入叛军，被武则天赐死。
   - forbidden: 武则天听信谗言将狄仁杰下狱并处斩，李元芳劫法场救走狄仁杰后远走他乡。

**6.** kind=`identity` subjects=`['袁天罡']`
   - statement: 袁天罡是蛇灵的创立者与精神导师，始终以反武复唐为旗帜。
   - forbidden: 袁天罡被设定为从始至终伪装成反派的朝廷忠臣，所有恶行都是为了揪出内奸。
   - forbidden: 袁天罡其实是武则天的秘密合作者，蛇灵组织是朝廷自导自演的清洗工具。

### forbidden_name_patterns

- 禁止给原创配角起名‘狄X’格式（如狄英、狄明），狄姓在本系列中专属狄仁杰及其子女，以免误认为狄氏家族成员。
- 禁止使用类似‘李X芳’的模板给非原作 NPC 取名（如李慧芳、李美芳），以免与李元芳的命名风格高度混淆，破坏角色辨识度。

### 关键人物（前 8 个）

- **狄仁杰** (绝对主角，当朝宰相，神探, must_have=True) — 关系: 自身即主角
- **李元芳** (狄仁杰的贴身护卫、最信任的助手, must_have=True) — 关系: 情同父子的主仆与战友
- **如燕** (前蛇灵杀手，后成为狄仁杰义女与李元芳恋人, must_have=True) — 关系: 狄仁杰的义女，李元芳的恋人
- **肖清芳** (蛇灵组织的大姐，系列首要反派之一, must_have=True) — 关系: 狄仁杰的宿敌
- **武则天** (大周皇帝，狄仁杰的君主与最高盟友/对手, must_have=False) — 关系: 君臣，既依赖又猜忌
- **曾泰** (狄仁杰的学生，从知县升迁至大理寺卿, must_have=False) — 关系: 弟子与得力助手

---

## 结论建议

（待人工填写：根据上面 verdict 决定 B 块走 anchor 路线 / 预定义字典 / 混合）
