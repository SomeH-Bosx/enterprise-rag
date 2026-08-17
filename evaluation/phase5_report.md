# Enterprise RAG — Phase5 评测报告

## 汇总

- 题目总数: **30**
- Recall@5: **86.67%** (26/30)
- 引用页码命中率: **0.7586206896551724**
- use_reranker: `True` · use_bm25: `True`
- elapsed_ms: `27796.39`

### RAGAS-style 指标

- 已跳过生成（`--skip-generation`）；未计算 RAGAS-style

## 明细

### Q1. 广东技术师范大学本科生奖学金管理办法中，奖学金设置了哪些种类？
- id: `hb-scholarship-kinds`
- expected_filename: `附件7：广东技术师范大学学生手册（2023年3月版）.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf']
- ground_truth: 国家奖学金、国家励志奖学金、单位(个人)专项奖学金、“自强标兵”奖学金、优秀学生奖学金和学校专项奖学金。

### Q2. 优秀三好学生奖学金的评选比例和奖金额分别是多少？
- id: `hb-excellent-three-good-amount`
- expected_filename: `附件7：广东技术师范大学学生手册（2023年3月版）.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', 'offer先生春招求职一本通PDF.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf']
- ground_truth: 按各学院参评学生人数1%的比例评选，奖金额为3000元/人。

### Q3. 三好学生奖学金按什么比例评选？奖金多少？
- id: `hb-three-good-amount`
- expected_filename: `附件7：广东技术师范大学学生手册（2023年3月版）.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 按各学院参评学生人数6%的比例评选，奖金额为2000元/人。

### Q4. 优秀学生干部奖学金的奖金额是多少？校级学生组织如何计算评选比例？
- id: `hb-cadre-scholarship`
- expected_filename: `附件7：广东技术师范大学学生手册（2023年3月版）.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 奖金额为800元/人；校学生会等校级组织分别按其学生干部人数15%的比例评选。

### Q5. 综合测评单项奖学金的评选比例和金额是多少？
- id: `hb-single-item-scholarship`
- expected_filename: `附件7：广东技术师范大学学生手册（2023年3月版）.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 按参评班级学生人数15%的比例评选，奖金额为500元/人。

### Q6. 优秀学术成果专项奖学金的特等奖和三等奖金额分别是多少？
- id: `hb-academic-special-awards`
- expected_filename: `附件7：广东技术师范大学学生手册（2023年3月版）.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 特等奖2000元/人，三等奖200元/人。

### Q7. 一学期内无故旷课达到多少节就不能享受优秀学生奖学金？
- id: `hb-absent-disqualify`
- expected_filename: `附件7：广东技术师范大学学生手册（2023年3月版）.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 一学期内无故旷课5节以上（含5节）者不能享受优秀学生奖学金和工作积极分子奖。

### Q8. 广师大评给表现最顶尖那一档“三好”荣誉的奖金大概是多少钱一个人？
- id: `hb-semantic-top-scholarship`
- expected_filename: `附件7：广东技术师范大学学生手册（2023年3月版）.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 优秀三好学生奖学金为3000元/人。

### Q9. 学生手册目录中，是否包含《广东技术师范大学学生违纪处分管理规定》？
- id: `hb-toc-has-discipline-rule`
- expected_filename: `附件7：广东技术师范大学学生手册（2023年3月版）.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf']
- ground_truth: 包含。目录下篇第十三项为《广东技术师范大学学生违纪处分管理规定》。

### Q10. 根据offer先生春招求职一本通，什么是春招？
- id: `offer-what-is-spring`
- expected_filename: `offer先生春招求职一本通PDF.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 春招即春季招聘：企业在秋招、补招后重新放出未招满或少量新开辟岗位，因在春季前后招聘而得名。

### Q11. 春招一般什么时候开始？高峰大概在哪几个月？
- id: `offer-spring-timeline`
- expected_filename: `offer先生春招求职一本通PDF.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 春节前就会开始，一般12月就有岗位；过年前有一波小高潮，过年后3-4月有大高潮。

### Q12. 春招和秋招、秋招补录相比，岗位量和招聘时间有什么特点？
- id: `offer-spring-vs-autumn`
- expected_filename: `offer先生春招求职一本通PDF.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 春招岗位种类少、总量少、招聘时间短；秋招规模最大岗位多时间长；补录岗位变少时间变短。

### Q13. 今年春招哪些人可以参与？
- id: `offer-who-can-apply`
- expected_filename: `offer先生春招求职一本通PDF.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 23届应届（22年下半年~23届上半年毕业）以及21-22届择业期同学均可参与；也有少量实习供24-25届申请。

### Q14. 材料中认为春招的难点主要有哪些？
- id: `offer-spring-difficulty`
- expected_filename: `offer先生春招求职一本通PDF.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 竞争压力更大、招聘时间更短、岗位量更少且选择面更窄。

### Q15. 春季校园招聘是不是一定要等到春天才能投？材料怎么说？
- id: `offer-semantic-when-recruit`
- expected_filename: `offer先生春招求职一本通PDF.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 春招一定不是春季才招聘；基本上春节前就会开始，12月就会有岗位放出。

### Q16. 简历写作部分提到的STAR法则是用来做什么的？
- id: `offer-keyword-star`
- expected_filename: `offer先生春招求职一本通PDF.pdf`
- hit_doc (Recall): **True**
- hit_page: None
- retrieved_files: ['offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 用STAR法则精简简历（目录与正文均有STAR法则相关章节）。

### Q17. 迪士尼客诉升级机制中，一线必须立即启动升级的通用触发门槛包括哪几类？
- id: `esc-seven-triggers`
- expected_filename: `迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx', '迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园——东京迪士尼解析-中英文版.pptx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx']
- ground_truth: 人身/财产安全事故；涉及执法或舆情风险；歧视或严重服务冒犯；高额赔偿诉求；连续二次投诉；政策与合同争议；系统级故障。

### Q18. 出现升级情形时，一线要在多长时间内通知当班主管，并在多长时间内交由宾客关系部或专业部门接手？
- id: `esc-time-limits`
- expected_filename: `迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx`
- hit_doc (Recall): **False**
- hit_page: False
- retrieved_files: ['offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 3分钟内通知当班主管，10分钟内交由宾客关系部（GR）或对应专业部门接手。

### Q19. 升级流程时间轴里，一线员工0–3分钟要用对讲机呼叫什么代码？
- id: `esc-code-g`
- expected_filename: `迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx`
- hit_doc (Recall): **False**
- hit_page: False
- retrieved_files: ['offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 呼叫“Code G”（Guest Escalation），同时填写《现场事件单》。

### Q20. 上海迪士尼高额赔偿诉求的升级门槛金额是多少？
- id: `esc-shanghai-threshold`
- expected_filename: `迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx']
- ground_truth: 上海：索赔金额＞当班主管当日授权上限，文档写明 >1000元。

### Q21. 客诉升级的一句话记忆卡片是什么？
- id: `esc-memory-card`
- expected_filename: `迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx`
- hit_doc (Recall): **False**
- hit_page: False
- retrieved_files: ['offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: “只要出现‘血、法、媒、钱、群、二、政’七个字，立刻升级！”

### Q22. 如果游客说要把事情发到网上或找媒体曝光，一线要不要升级？依据是什么？
- id: `esc-semantic-media-threat`
- expected_filename: `迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx`
- hit_doc (Recall): **False**
- hit_page: False
- retrieved_files: ['offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 要升级。属于“涉及执法或舆情风险”（声称联系媒体或社交平台曝光等）。

### Q23. 材料中迪士尼乐园酒店的入住和退房时间分别是什么？
- id: `hotel-checkin-checkout`
- expected_filename: `迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园——东京迪士尼解析-中英文版.pptx', '迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx']
- ground_truth: 入住时间为15:00过后，退房时间为11:00之前。

### Q24. 中国香港迪士尼乐园酒店每晚价格低至多少？
- id: `hotel-hk-price`
- expected_filename: `迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx']
- ground_truth: 每晚价格低至¥934。

### Q25. 迪士尼乐园酒店宾客专属福利中的“超时神奇体验（Extra Magic Hour）”是什么意思？
- id: `hotel-extra-magic-hour`
- expected_filename: `迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园——东京迪士尼解析-中英文版.pptx']
- ground_truth: 每天可在指定主题乐园对大众开放前一小时提前游玩特定游乐项目。

### Q26. 东京迪士尼乐园向公众开放的日期是哪一天？
- id: `tdl-open-date`
- expected_filename: `迪士尼乐园——东京迪士尼解析-中英文版.pptx`
- hit_doc (Recall): **True**
- hit_page: False
- retrieved_files: ['迪士尼乐园——东京迪士尼解析-中英文版.pptx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园——东京迪士尼解析-中英文版.pptx', '迪士尼乐园——东京迪士尼解析-中英文版.pptx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx']
- ground_truth: 1983年4月15日向公众开放。

### Q27. 东京迪士尼由谁运营？与迪士尼公司的分成比例是怎样的？
- id: `tdl-oriental-land-contract`
- expected_filename: `迪士尼乐园——东京迪士尼解析-中英文版.pptx`
- hit_doc (Recall): **True**
- hit_page: False
- retrieved_files: ['迪士尼乐园——东京迪士尼解析-中英文版.pptx', '迪士尼乐园——东京迪士尼解析-中英文版.pptx', '迪士尼乐园——东京迪士尼解析-中英文版.pptx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx', '迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx']
- ground_truth: 由Oriental Land（东方乐园）在华特迪士尼公司许可下拥有和经营；45年合约中迪士尼获得入场费10%、餐饮商品销售5%，另加授权费；迪士尼不占股、不出资建设。

### Q28. 材料提到1983年8月13日东京迪士尼单日入园大约多少人？四年后刷新纪录时又是多少？
- id: `tdl-attendance-record`
- expected_filename: `迪士尼乐园——东京迪士尼解析-中英文版.pptx`
- hit_doc (Recall): **True**
- hit_page: False
- retrieved_files: ['迪士尼乐园——东京迪士尼解析-中英文版.pptx', '迪士尼乐园——东京迪士尼解析-中英文版.pptx', '迪士尼乐园——东京迪士尼解析-中英文版.pptx', '迪士尼乐园——东京迪士尼解析-中英文版.pptx', '迪士尼乐园——东京迪士尼解析-中英文版.pptx']
- ground_truth: 1983年8月13日约93000人；四年后纪录为111500人。

### Q29. 宾客关系部（Guest Relations）在客诉升级中扮演什么角色？另，迪士尼乐园酒店退房一般在几点前？
- id: `xdoc-disney-gr-and-hotel-time`
- expected_filename: `迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx', '迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx', '迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx', '迪士尼乐园度假区客诉升级处理机制：何时需要将问题转给上级或特定部门（如：宾客关系部）.docx', '迪士尼乐园酒店信息 包括各家迪士尼酒店的房型、定价、设施（泳池、健身房）、入住_退房政策和酒店宾客专属福利.docx']
- ground_truth: GR为升级接手部门之一；酒店材料写明退房时间为11:00之前（见酒店信息文档）。

### Q30. 广东技术师范大学学生手册里的奖学金条款，会不会规定迪士尼客诉升级的Code G流程？
- id: `xdoc-school-vs-disney`
- expected_filename: `附件7：广东技术师范大学学生手册（2023年3月版）.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', '附件7：广东技术师范大学学生手册（2023年3月版）.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 不会。学生手册奖学金章节不涉及迪士尼Code G；Code G在客诉升级文档中。
