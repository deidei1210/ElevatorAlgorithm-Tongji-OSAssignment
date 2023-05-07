import sys
# 导入PyQT5模块，用来绘制界面图像
from PyQt5.QtCore import QRect, QThread, QMutex, QTimer,Qt
from PyQt5.QtWidgets import QWidget, QPushButton, QApplication, QLabel, QTextEdit, QVBoxLayout, QHBoxLayout, QLCDNumber, \
    QLineEdit
# import time
from enum import Enum  # 枚举类
from functools import partial  # 使button的connect函数可带参数


# gui窗口大小设置
WINDOW_SIZE = QRect(200, 200, 1100, 800)

# 一些全局变量
ELEVATOR_NUM = 5  # 电梯数量
ELEVATOR_FLOORS = 20  # 电梯层数

TIME_PER_FLOOR = 800  # 运行一层电梯所需时间 单位 毫秒
OPENING_DOOR_TIME = 500  # 打开一扇门所需时间 单位 毫秒
OPEN_DOOR_TIME = 500  # 门打开后维持的时间 单位 毫秒

# 全局变量定义
# 每组电梯的状态
elevator_states = []
# 每台电梯当前的扫描运行状态
elevator_move_states = []
# 每台电梯的当前楼层
elevator_cur_floor = []
# 电梯在向上扫描的过程中，还需要处理的任务（二维数组），每个一维数组表示一个电梯的情况
up_remains = []
# 电梯在向下扫描的过程中，还需要处理的任务（二维数组），每个一维数组表示一个电梯的情况
down_remains = []
# 每台电梯内部的开门/关门键是否被按（True/False）
open_button_clicked = []
close_button_clicked = []
# 每台电梯开门的进度条 范围为0-1的浮点数
open_progress = []
#每个电梯的门
Doors=[]
# 外部按钮产生的事件
outer_button_events = []
# mutex互斥锁
mutex = QMutex()

# 电梯的扫描移动状态枚举，这个枚举中包含了电梯扫描的两种可能的状态，一个是向上一个是向下
class MoveState(Enum):
    up = 2          #电梯在向上扫描的状态中
    down = 3        #电梯在向下扫描的状态中

# 电梯状态的枚举，这个枚举中集合了电梯所有可能的状态
class ElevatorState(Enum):
    normal = 0       #表示电梯状态是正常的
    fault = 1        #表示电梯此时状态是故障的状态
    opening_door = 2 #表示电梯正在开门
    open_door = 3    #表示电梯门已经打开
    closing_door = 4 #表示电梯正在关门
    going_up = 5     #表示电梯正在上行
    going_down = 6   #表示电梯正在下行

# 外部按钮可能处在的状态，这个枚举中包含了电梯外部每个楼层的电梯按钮的状态
class OuterButtonState(Enum):
    unassigned = 1   #表示该按钮没有被按下
    waiting = 2      #表示该按钮已经被按下，正在等待被处理
    finished = 3     #表示该按钮的任务已经被完成

# 外部按钮按下产生的任务描述
class OuterButtonGenerateTask:
    def __init__(self, target, move_state, state=OuterButtonState.unassigned):  # the task is unfinished by default
        self.target = target  # 目标楼层
        self.move_state = move_state  # 需要的电梯运行方向
        self.state = state  # 是否完成（默认未完成）


#对每个电梯先赋初值
for i in range(ELEVATOR_NUM):
    # inner_requests.append([])  # add list
    elevator_states.append(ElevatorState.normal)  # 默认正常
    elevator_cur_floor.append(1)  # 默认在1楼
    up_remains.append([])  # 二维数组
    down_remains.append([])  # 二维数组
    
    close_button_clicked.append(False)  # 默认开门关门键没按
    open_button_clicked.append(False)
    elevator_move_states.append(MoveState.up)  # 默认向上（一开始在1楼 只能向上
    open_progress.append(0.0)  # 默认门没开 即进度条停在0.0

class Elevator(QThread):  # 继承Qthread
    def __init__(self, elev_id):
        super().__init__()  # 父类构造函数
        self.elev_id = elev_id  # 电梯编号
        self.gap_time = 10  # 时间间隔（单位：毫秒）

    # 移动一层楼
    # 方向由参数确定 可以是
    # MoveState.up or MoveState.down
    def lift_up_one_floor(self, move_state):
        # 修改电梯运行状态
        #如果电梯当前的扫描运行状态是向上，那么就将当前电梯的运行状态改成向上运行
        if move_state == MoveState.up:
            elevator_states[self.elev_id] = ElevatorState.going_up
        #如果当前电梯的扫描状态是向下，那么就将当前电梯的运行状态改成向下运行
        elif move_state == MoveState.down:
            elevator_states[self.elev_id] = ElevatorState.going_down

        has_slept_time = 0
        #每过一个gap_time的时间就需要检查一下电梯是否故障，直到运行完一整个楼层
        while has_slept_time != TIME_PER_FLOOR:
            # 需要先放开锁 不然别的线程不能运行
            mutex.unlock()
            #休眠gap_time毫秒，在用户看来就是这段时间电梯在向上运行
            self.msleep(self.gap_time)  # 时间间隔（单位：毫秒）
            has_slept_time += self.gap_time 
            # 锁回来
            mutex.lock()
            # 如果此时出故障了，就需要进行相应的故障处理
            if elevator_states[self.elev_id] == ElevatorState.fault:
                self.fault_tackle()
                return
        
        #电梯一层已经运行完毕，对相应的扫描方向做相应的所在楼层的更改
        if move_state == MoveState.up:
            elevator_cur_floor[self.elev_id] += 1
        elif move_state == MoveState.down:
            elevator_cur_floor[self.elev_id] -= 1
        elevator_states[self.elev_id] = ElevatorState.normal
        # print(self.elev_id, "号现在在", elevator_cur_floor[self.elev_id], "楼")
        if elevator_states[self.elev_id] == ElevatorState.fault:
            self.fault_tackle()

    # 一次门的操作 包括开门和关门
    def door_operation(self):
        opening_time = 0.0
        open_time = 0.0
        elevator_states[self.elev_id] = ElevatorState.opening_door
        while True:
            if elevator_states[self.elev_id] == ElevatorState.fault:
                self.fault_tackle()
                break
            #如果用户按下了开门的键
            elif open_button_clicked[self.elev_id] == True:
                # 门正在关上..
                if elevator_states[self.elev_id] == ElevatorState.closing_door:
                    elevator_states[self.elev_id] = ElevatorState.opening_door

                # 门已经开了，延续开门时间
                if elevator_states[self.elev_id] == ElevatorState.open_door:
                    open_time = 0
                #门的状态相关信息已经更新，将其状态重新设置为未点击的状态
                open_button_clicked[self.elev_id] = False
            #如果用户按下了关门键
            elif close_button_clicked[self.elev_id] == True:
                elevator_states[self.elev_id] = ElevatorState.closing_door
                open_time = 0

                close_button_clicked[self.elev_id] = False

            # 更新时间
            # 门正在打开
            if elevator_states[self.elev_id] == ElevatorState.opening_door:
                # 需要先放开锁 不然别的线程不能运行
                mutex.unlock()
                self.msleep(self.gap_time )
                opening_time += self.gap_time 
                # 锁回来
                mutex.lock()
                open_progress[self.elev_id] = opening_time / OPENING_DOOR_TIME
                
                if opening_time == OPENING_DOOR_TIME:
                    elevator_states[self.elev_id] = ElevatorState.open_door

            # 门已打开
            elif elevator_states[self.elev_id] == ElevatorState.open_door:
                # 需要先放开锁 不然别的线程不能运行
                mutex.unlock()
                self.msleep(self.gap_time )
                open_time += self.gap_time 
                # 锁回来
                mutex.lock()
                if open_time == OPEN_DOOR_TIME:
                    elevator_states[self.elev_id] = ElevatorState.closing_door

            # 门正在关闭
            elif elevator_states[self.elev_id] == ElevatorState.closing_door:
                # 需要先放开锁 不然别的线程不能运行
                mutex.unlock()
                self.msleep(self.gap_time )
                opening_time -= self.gap_time 
                # 锁回来
                mutex.lock()
                open_progress[self.elev_id] = opening_time / OPENING_DOOR_TIME
                if opening_time == 0:
                    # 门关好了 润回去咯
                    elevator_states[self.elev_id] = ElevatorState.normal
                    break

    # 当故障发生时 清除原先的所有任务
    def fault_tackle(self):
        elevator_states[self.elev_id] = ElevatorState.fault
        open_progress[self.elev_id] = 0.0
        open_button_clicked[self.elev_id] = False
        close_button_clicked[self.elev_id] = False
        elevator_states[self.elev_id] = ElevatorState.fault
        for outer_task in outer_button_events:
            if outer_task.state == OuterButtonState.waiting:
                if outer_task.target in up_remains[self.elev_id] or outer_task.target in down_remains[self.elev_id]:
                    outer_task.state = OuterButtonState.unassigned  # 把原先分配给它的任务交给handler重新分配
        up_remains[self.elev_id] = []
        down_remains[self.elev_id] = []

    def run(self):
        while True:
            mutex.lock()
            if elevator_states[self.elev_id] == ElevatorState.fault:
                self.fault_tackle()
                mutex.unlock()
                continue

            # 向上扫描状态时
            if elevator_move_states[self.elev_id] == MoveState.up:
                #如果上面还有未完成的任务，即电梯的上面还有请求没有满足
                if up_remains[self.elev_id] != []:
                    #如果已经到达了目标楼层
                    if up_remains[self.elev_id][0] == elevator_cur_floor[self.elev_id]:
                        self.door_operation()
                        # 到达以后 把完成的任务删去
                        # 内部的任务
                        if up_remains != []:
                            up_remains[self.elev_id].pop(0)
                        # 外部按钮的任务
                        for outer_task in outer_button_events:
                            if outer_task.target == elevator_cur_floor[self.elev_id]:
                                outer_task.state = OuterButtonState.finished  # 交给handler处理
                    elif up_remains[self.elev_id][0] > elevator_cur_floor[self.elev_id]:
                        self.lift_up_one_floor(MoveState.up)

                # 当没有上行目标而出现下行目标时 更换状态
                elif up_remains[self.elev_id] == [] and down_remains[self.elev_id] != []:
                    elevator_move_states[self.elev_id] = MoveState.down

            # 向下扫描状态时
            elif elevator_move_states[self.elev_id] == MoveState.down:
                if down_remains[self.elev_id] != []:
                    if down_remains[self.elev_id][0] == elevator_cur_floor[self.elev_id]:
                        self.door_operation()
                        # 到达以后 把完成的任务删去
                        # 内部的任务
                        if down_remains != []:
                            down_remains[self.elev_id].pop(0)
                        # 外部按钮的任务
                        for outer_task in outer_button_events:
                            if outer_task.target == elevator_cur_floor[self.elev_id]:
                                outer_task.state = OuterButtonState.finished

                    elif down_remains[self.elev_id][0] < elevator_cur_floor[self.elev_id]:
                        self.lift_up_one_floor(MoveState.down)

                # 当没有下行目标而出现上行目标时 更换状态
                elif down_remains[self.elev_id] == [] and up_remains[self.elev_id] != []:
                    elevator_move_states[self.elev_id] = MoveState.up

            mutex.unlock()

# controller用于处理外面按钮产生的任务，并选择合适的相应的电梯，将任务添加到对应电梯的任务列表中
class OuterTaskController(QThread):
    def __init__(self):
        super().__init__()  # 父类构造函数

    def run(self):
        while True:
            mutex.lock()
            global outer_button_events
            
            # 找到距离最短的电梯的id
            for outer_task in outer_button_events:
                if outer_task.state == OuterButtonState.unassigned:  # 如果还没有把这个按钮的任务分配给任意的电梯
                    #先初始化最短距离为电梯楼层数+1
                    min_distance = ELEVATOR_FLOORS + 1
                    target_id = -1
                    #寻找目前可以最快响应的电梯
                    for i in range(ELEVATOR_NUM):
                        # 符合要求的电梯，必须没有故障，所以如果这个电梯是故障电梯，那么直接淘汰
                        if elevator_states[i] == ElevatorState.fault:
                            continue

                        # 如果已经上行/下行了 就设成已经到达目的地的楼层了
                        origin = elevator_cur_floor[i]
                        if elevator_states[i] == ElevatorState.going_up:
                            origin += 1
                        elif elevator_states[i] == ElevatorState.going_down:
                            origin -= 1

                        #如果电梯的运行状态是向上的，那么就将该电梯上面的待处理的所有任务的一维数组赋值给targets
                        if elevator_move_states[i] == MoveState.up:
                            targets = up_remains[i]
                        else:  #如果下行，就把下面的待处理任务给targets
                            targets = down_remains[i]

                        # 本身对某一种方向来说，根据这部电梯是否与它运行方向相同，是在上方还是下方，是否有任务，分为8种情况.
                        # 如果电梯运行方向无任务，则直接算绝对值
                        if targets == []:
                            distance = abs(origin - outer_task.target)
                        # 如果电梯朝着按键所在楼层而来 且运行方向与理想方向相同 也是直接绝对值
                        elif elevator_move_states[i] == outer_task.move_state and \
                                ((outer_task.move_state == MoveState.up and outer_task.target >= origin) or
                                 (outer_task.move_state == MoveState.down and outer_task.target <= origin)):
                            distance = abs(origin - outer_task.target)
                        # 其余情况则算最远任务楼层到目标楼层的绝对值和最远楼层到当前电梯楼层的绝对值之和
                        else:
                            distance = abs(origin - targets[-1]) + abs(outer_task.target - targets[-1])

                        # 寻找最小值
                        if distance < min_distance:
                            min_distance = distance
                            target_id = i

                    # 假如找到了 对应添加任务
                    if target_id != -1:
                        if elevator_cur_floor[target_id] == outer_task.target:
                            if outer_task.move_state == MoveState.up and outer_task.target not in up_remains[
                                target_id] and elevator_states[target_id] != ElevatorState.going_up:
                                up_remains[target_id].append(outer_task.target)
                                up_remains[target_id].sort()
                                
                                # 设为等待态
                                outer_task.state = OuterButtonState.waiting

                            elif outer_task.move_state == MoveState.down and outer_task.target not in down_remains[
                                target_id] and elevator_states[target_id] != ElevatorState.going_down:
                                down_remains[target_id].append(outer_task.target)
                                down_remains[target_id].sort(reverse=True)  # 这里需要降序！ 例如，[20,19,..1]
                                # print(down_targets)
                                # 设为等待态
                                outer_task.state = OuterButtonState.waiting

                        elif elevator_cur_floor[target_id] < outer_task.target and outer_task.target not in up_remains[
                            target_id]:  # up
                            up_remains[target_id].append(outer_task.target)
                            up_remains[target_id].sort()
                            # print(up_remains)
                            # 设为等待态
                            outer_task.state = OuterButtonState.waiting
                        elif elevator_cur_floor[target_id] > outer_task.target and outer_task.target not in down_remains[
                            target_id]:  # down
                            down_remains[target_id].append(outer_task.target)
                            down_remains[target_id].sort(reverse=True)  # 这里需要降序！ 例如，[20,19,..1]
                            # print(down_targets)
                            # 设为等待态
                            outer_task.state = OuterButtonState.waiting

            # 查看哪些任务已经完成了 移除已经完成的
            outer_button_events = [task for task in outer_button_events if task.state != OuterButtonState.finished]

            mutex.unlock()


# 图形化界面 同时处理画面更新和输入
class ElevatorUi(QWidget):
    def __init__(self):
        super().__init__()  # 父类构造函数
        self.output = None
        # 各种需要更新的按钮 显示屏等收集
        self.__floor_displayers = []   #电梯上方的显示屏
        self.__inner_num_buttons = []
        self.__inner_open_buttons = []
        self.__inner_close_buttons = []
        self.__outer_up_buttons = []
        self.__outer_down_buttons = []
        self.__inner_fault_buttons = []

        # 定时器 用于定时更新UI界面
        self.timer = QTimer()
        #每个电梯的门的计时器
        self.door_timer=[]
        # 设置UI
        self.setup_ui()

    # 设置UI
    def setup_ui(self):
        self.setWindowTitle("2051498储岱泽——电梯调度")
        self.setGeometry(WINDOW_SIZE)

        h1 = QHBoxLayout()
        self.setLayout(h1)

        #布局右边的上下按钮
        v3 = QVBoxLayout()#创建一个垂直布局
        h1.addLayout(v3)
        #标题
        title_outer=QLabel("外部按钮")
        v3.addWidget(title_outer)
        v3.setAlignment(title_outer, Qt.AlignHCenter)

        for i in range(ELEVATOR_FLOORS):#对于每一层楼
            h4 = QHBoxLayout() #创建一个水平布局
            v3.addLayout(h4)
            label = QLabel(str(ELEVATOR_FLOORS - i))
            h4.addWidget(label)
            if i != 0:
                # 给2楼到顶楼放置上行按钮
                up_button = QPushButton("↑")
                up_button.setFixedSize(30, 30)
                up_button.clicked.connect(
                    partial(self.__outer_direction_button_clicked, ELEVATOR_FLOORS - i, MoveState.up))
                self.__outer_up_buttons.append(up_button)  # 从顶楼往下一楼开始..
                h4.addWidget(up_button)

            if i != ELEVATOR_FLOORS - 1:
                # 给1楼到顶楼往下一楼放置下行按钮
                down_button = QPushButton("↓")
                down_button.setFixedSize(30, 30)
                down_button.clicked.connect(
                    partial(self.__outer_direction_button_clicked, ELEVATOR_FLOORS - i, MoveState.down))
                self.__outer_down_buttons.append(down_button)  # 从顶楼开始..到2楼
                h4.addWidget(down_button)
        

        h2 = QHBoxLayout()
        h1.addLayout(h2)

        #对每一个电梯都进行相同的设置
        for i in range(ELEVATOR_NUM):
            v2 = QVBoxLayout()   #竖直布局
            h2.addLayout(v2)

            # 电梯上方的LCD显示屏
            floor_display = QLCDNumber() #定义了一个LCD显示屏，用来显示电梯当前所在的楼层数
            # 将显示屏的位数设置为 2
            floor_display.setNumDigits(2)
            # 将段的样式设置为 Flat，使数字居中显示
            floor_display.setSegmentStyle(QLCDNumber.Flat)
            # 设置样式表，将数字颜色设为红色
            floor_display.setStyleSheet("color: rgb(165,93,81);")
            floor_display.setFixedSize(100, 50) #LCD显示屏的大小
            self.__floor_displayers.append(floor_display)
            v2.addWidget(floor_display)       #将该LCD添加到v2布局中
           
            #添加文字提示
            Text=QLabel("电梯"+str(i+1)+"内部按钮",self)
            v2.addWidget(Text)
            v2.addStretch()

            # 故障按钮
            fault_button = QPushButton("故障")
            fault_button.setFixedSize(100, 30)
            fault_button.clicked.connect(partial(self.__inner_fault_button_clicked, i))
            self.__inner_fault_buttons.append(fault_button)
            v2.addWidget(fault_button)

            #设置每一个电梯的内部按钮
            self.__inner_num_buttons.append([])
            elevater_button_layout = QHBoxLayout()   #用来水平的排列每排按钮
            # 创建电梯按钮
            button_group1 = QVBoxLayout()  # 前10层按钮
            for j in range(1,int(ELEVATOR_FLOORS/2+1)):
                button = QPushButton(str(int(ELEVATOR_FLOORS/2+1-j)))
                button.setFixedSize(30, 30)
             
                #绑定点击每一个楼层的按钮后的事件
                button.clicked.connect(partial(self.__inner_num_button_clicked, i, int(ELEVATOR_FLOORS/2+1-j)))
                button.setStyleSheet("background-color : rgb(31,59,84);""border-style: solid;"
                          "border-width: 2px;"
                          "border-color:  rgb(165,93,81);"
                          "border-radius:10px;"
                          "color:white;")
                self.__inner_num_buttons[i].append(button)
                button_group1.addWidget(button)
             # 增大元素之间的竖直方向距离
            button_group1.setSpacing(10)

            # 开门按钮
            open_button = QPushButton("开")
            open_button.setFixedSize(30, 30)
            open_button.clicked.connect(partial(self.__inner_open_button_clicked, i))
            self.__inner_open_buttons.append(open_button)
            open_button.setStyleSheet("background-color :rgb(237,220,195);""border-style: solid;"
                          "border-width: 2px;"
                          "border-color: rgb(165,93,81);"
                          "border-radius:10px;"
                          "color:black;")
            button_group1.addWidget(open_button)
            

            button_group2 = QVBoxLayout()  # 后10层按钮
            for j in range(1, int(ELEVATOR_FLOORS/2+1)):
                button = QPushButton(str(ELEVATOR_FLOORS+1-j))
                button.setFixedSize(30, 30)
                
                #绑定点击每一个楼层的按钮后的事件
                button.clicked.connect(partial(self.__inner_num_button_clicked, i,ELEVATOR_FLOORS+1-j))
                button.setStyleSheet("background-color :rgb(31,59,84);""border-style: solid;"
                          "border-width: 2px;"
                          "border-color: rgb(165,93,81);"
                          "border-radius:10px;"
                          "color:white;")
                self.__inner_num_buttons[i].append(button)
                button_group2.addWidget(button)
            button_group2.setSpacing(10)

            # 关门按钮
            close_button = QPushButton("关")
            close_button.setFixedSize(30, 30)
            close_button.clicked.connect(partial(self.__inner_close_button_clicked, i))
            close_button.setStyleSheet("background-color :rgb(237,220,195);""border-style: solid;"
                          "border-width: 2px;"
                          "border-color: rgb(165,93,81);"
                          "border-radius:10px;"
                          "color:black;")
            self.__inner_close_buttons.append(close_button)
            button_group2.addWidget(close_button)

            # 将 button_group1 添加到 elevater_button_layout 中
            button_group1_widget = QWidget()
            button_group1_widget.setLayout(button_group1)  # 嵌套一下 QVBoxLayout
            elevater_button_layout.addWidget(button_group1_widget)
            # 将 button_group1 添加到 elevater_button_layout 中
            button_group2_widget = QWidget()
            button_group2_widget.setLayout(button_group2)  # 嵌套一下 QVBoxLayout   
            elevater_button_layout.addWidget(button_group2_widget)

            elevater_button_layout_widget = QWidget()
            elevater_button_layout_widget.setLayout(elevater_button_layout)  # 嵌套一下 QHBoxLayout
            v2.addWidget(elevater_button_layout_widget)
            v2.addStretch()
            #接下来给v2添加门
            door=[]
            # 创建四个充当门的按钮的水平布局
            hbox1 = QHBoxLayout()
            for d in range(4):
                DoorTimer=QTimer()
                self.door_timer.append(DoorTimer)
                button = QPushButton('', self)
                button.setFixedSize(40,80) 
                door.append(button)
                hbox1.addWidget(button)
            door[0].setStyleSheet('background-color: transparent;')
            door[1].setStyleSheet('background-color: black;')
            door[2].setStyleSheet('background-color: black;')
            door[3].setStyleSheet('background-color: transparent;')
            Doors.append(door) #将这扇门添加进Doors中
            hbox1_widget=QWidget()
            hbox1_widget.setLayout(hbox1)
            v2.addWidget(hbox1_widget)
            
            #添加文字提示
            Text1=QLabel("电梯"+str(i+1)+"的门",self)
            v2.addWidget(Text1)
            # v2.addStretch()

            v2.addStretch()
            # 设置布局中的组件水平居中
            v2.setAlignment(floor_display, Qt.AlignHCenter)
            v2.setAlignment(fault_button, Qt.AlignHCenter)
            v2.setAlignment(elevater_button_layout_widget, Qt.AlignHCenter)
            v2.setAlignment(hbox1_widget, Qt.AlignHCenter)
            v2.setAlignment(Text, Qt.AlignHCenter)
            v2.setAlignment(Text1, Qt.AlignHCenter)
            
            
            # v2.addLayout(h3)
            # h3.addWidget(open_button)
            # h3.addWidget(close_button)
        
 
        v1 = QVBoxLayout()
        h1.addLayout(v1)
        title1=QLabel("电梯控制台")
        title1.setStyleSheet("font-size:24px;""font-weight:bold;")
        v1.addWidget(title1)
        v1.setAlignment(title1, Qt.AlignHCenter)
          # 接收用户输入的产生任务的数量
        instruction1=QLabel("请输入期望随机产生的电梯任务数量:\n")
        v1.addWidget(instruction1)
        self.generate_num_edit = QLineEdit()
        self.generate_num_edit.setText("0")
        v1.addWidget(self.generate_num_edit)
        button = QPushButton()
        button.setText("点我随机产生电梯任务！")
        button.setStyleSheet("background-color :rgb(165,93,81);""border-style: solid;"
                          "border-width: 2px;"
                          "border-color:  rgb(165,93,81);"
                          "border-radius:3px;"
                          "color:white;")
        button.clicked.connect(self.__generate_tasks)
        v1.addWidget(button)

        # 输出电梯信息
        self.output = QTextEdit()
        self.output.setText("电梯运行信息如下所示：\n")
        v1.addWidget(self.output)
        #电梯使用指南标题
        title=QLabel("\n\n电梯使用指南")
        title.setStyleSheet("font-size:20px;""font-weight:bold;")
        v1.addWidget(title)
        #放置电梯的使用说明
        instruction = QLabel("\n-------------------------------------------\n界面的中央表示五个电梯\n每个电梯有一个数码显示屏用于显示当前电梯所在的楼层\n显示屏下面显示的是每个电梯内部20个楼层按钮\n按下按钮将前往相应的楼层\n按钮下面有门，模仿电梯门的开关\n界面的左边是楼层外部的按键\n按下“上箭头”表示该楼层有用户想上楼\n按下“下箭头”表示该楼层有用户想下楼\n-------------------------------------------\n2051498储岱泽\n\n\n\n")
        instruction.setStyleSheet("font-size:16px;")
        v1.addWidget(instruction)

      

        # 设置定时
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.update)
        self.timer.start()

        self.show()

    #用于开门
    def open_the_door(self,elevator_id,choice):
        # print(Doors)
        Doors[elevator_id][0].setStyleSheet('background-color: black;')
        Doors[elevator_id][1].setStyleSheet('background-color: gray;')
        Doors[elevator_id][2].setStyleSheet('background-color: gray;')
        Doors[elevator_id][3].setStyleSheet('background-color: black;')
        Doors[elevator_id][1].hide()
        Doors[elevator_id][2].setFixedSize(80,80)
        # 需要先放开锁 不然别的线程不能运行
        # mutex.unlock()
        # self.msleep(1000)
        # open_time += self.time_slice
        # 锁回来
        # mutex.lock()
        # self.close_the_door(elevator_id)
        if choice:
         #创建一个 QTimer，设定 1 秒后触发 timeout 信号
            # self.Time_open=QTimer()
            self.door_timer[elevator_id].setInterval(4000)
            self.door_timer[elevator_id].timeout.connect(lambda:self.close_after_1s(elevator_id))
            self.door_timer[elevator_id].start()
    #用于关门
    def close_the_door(self,elevator_id):
        # print(Doors)
        Doors[elevator_id][0].setStyleSheet('background-color: transparent;')
        Doors[elevator_id][1].setStyleSheet('background-color: black;')
        Doors[elevator_id][2].setStyleSheet('background-color: black;')
        Doors[elevator_id][3].setStyleSheet('background-color: transparent;')
        Doors[elevator_id][1].show()
        Doors[elevator_id][2].setFixedSize(40,80)

    #用于随机产生任务
    def __generate_tasks(self):
        import random
        for i in range(int(self.generate_num_edit.text())):
            if random.randint(0, 100) < 30:  # 30% 产生外部任务
                rand = random.randint(1, ELEVATOR_FLOORS)
                if rand == 1:  # 1楼只能向上
                    self.__outer_direction_button_clicked(1, MoveState.up)
                elif rand == ELEVATOR_FLOORS:  # 顶楼只能向下
                    self.__outer_direction_button_clicked(rand, MoveState.down)
                else:  # 其余则随机指派方向
                    self.__outer_direction_button_clicked(rand, random.choice([MoveState.up, MoveState.down]))
            else:  # 产生内部任务
                self.__inner_num_button_clicked(random.randint(0, ELEVATOR_NUM - 1), random.randint(1, ELEVATOR_FLOORS))

    #处理指定电梯的开门请求
    def __inner_open_button_clicked(self, elevator_id):
        mutex.lock()
        #电梯故障
        if elevator_states[elevator_id] == ElevatorState.fault:
            self.output.append(str(elevator_id) + "号电梯出现故障 正在维修!")
            mutex.unlock()
            return
        #电梯正在关门或者正在开门
        if elevator_states[elevator_id] == ElevatorState.closing_door or elevator_states[
            elevator_id] == ElevatorState.open_door:
            open_button_clicked[elevator_id] = True
            close_button_clicked[elevator_id] = False
        mutex.unlock()
        #开门按钮

        self.__inner_open_buttons[elevator_id].setStyleSheet("background-color : rgb(165,93,81)")
        self.output.append(str(elevator_id) + "电梯开门!")
        #调用开门函数
        self.open_the_door(elevator_id,1)
    
    def close_after_1s(self, elevator_id):
        print(999)
        #调用关门函数
        self.close_the_door(elevator_id)
        #关闭定时器
        self.door_timer[elevator_id] = self.sender()  # 获取信号发送者
        self.door_timer[elevator_id].stop()
        # 设置定时
        # timer.setInterval(30)
        # timer.timeout.connect(self.update)
        # timer.start()

        # timer.deleteLater()
        
    #处理电梯关门事件
    def __inner_close_button_clicked(self, elevator_id):
        mutex.lock()
        if elevator_states[elevator_id] == ElevatorState.fault:
            self.output.append(str(elevator_id) + "号电梯出现故障 正在维修!")
            mutex.unlock()
            return

        if elevator_states[elevator_id] == ElevatorState.opening_door or elevator_states[
            elevator_id] == ElevatorState.open_door:
            close_button_clicked[elevator_id] = True
            open_button_clicked[elevator_id] = False
        mutex.unlock()
        #关门按钮
        self.__inner_close_buttons[elevator_id].setStyleSheet("background-color : rgb(165,93,81)")
        self.output.append(str(elevator_id) + "电梯关门!")
        self.close_the_door(elevator_id)
    #处理电梯故障
    def __inner_fault_button_clicked(self, elevator_id):
        mutex.lock()
        #如果电梯本来没有故障，那就设置成故障
        if elevator_states[elevator_id] != ElevatorState.fault:
            elevator_states[elevator_id] = ElevatorState.fault
            mutex.unlock()
            #将电梯的状态设置为损坏之后，改变其样式
            self.__inner_fault_buttons[elevator_id].setStyleSheet("background-color : gray;")
            for button in self.__inner_num_buttons[elevator_id]:
                button.setStyleSheet("background-color :gray;""border-radius:10px;")
            self.__inner_open_buttons[elevator_id].setStyleSheet("background-color : gray;")
            self.__inner_close_buttons[elevator_id].setStyleSheet("background-color : gray;")

            self.output.append(str(elevator_id) + "电梯故障!")
        #如果电梯本来就有故障，则再点一下故障就会消失
        else:
            elevator_states[elevator_id] = ElevatorState.normal
            mutex.unlock()

            self.__inner_fault_buttons[elevator_id].setStyleSheet("background-color : None")
            for button in self.__inner_num_buttons[elevator_id]:
                button.setStyleSheet("background-color :rgb(31,59,84);""border-style: solid;"
                          "border-width: 2px;"
                          "border-color: rgb(165,93,81);"
                          "border-radius:10px;"
                          "color:white;")
            self.__inner_open_buttons[elevator_id].setStyleSheet("background-color : None;")
            self.__inner_close_buttons[elevator_id].setStyleSheet("background-color : None;")
            self.output.append(str(elevator_id) + "电梯正常!")

    #如果按的是电梯内部的数字按钮，则执行下面的函数进行处理
    def __inner_num_button_clicked(self, elevator_id, floor):
        mutex.lock()
        #如果电梯出现故障
        if elevator_states[elevator_id] == ElevatorState.fault:
            self.output.append(str(elevator_id) + "号电梯出现故障 正在维修!")
            mutex.unlock()
            return
        
        # 相同楼层不处理
        if floor == elevator_cur_floor[elevator_id]:
            mutex.unlock()
            return

        if elevator_states[elevator_id] != ElevatorState.fault:
            #用户在电梯内请求前往的楼层大于当前楼层，且楼层不在已有的目标楼层中
            #在这边我们将在当前楼层之上的用户的请求集中在up_targets数组之中，并且将该数组中的数字从小到大排序；
            #        将位于当前楼层之下的请求集中在down_targets数组之中，并且将该数组中的数字从大到小排序；
            #        这样做是为了使得电梯总是访问当前方向上最近的楼层用户的请求
            if floor > elevator_cur_floor[elevator_id] and floor not in up_remains[elevator_id]:
                up_remains[elevator_id].append(floor)#将该楼添加到上行的目标楼层中
                up_remains[elevator_id].sort()       #按照从小到大的顺序排序
            elif floor < elevator_cur_floor[elevator_id] and floor not in down_remains[elevator_id]:
                down_remains[elevator_id].append(floor)
                down_remains[elevator_id].sort(reverse=True)  # 降序排序

            mutex.unlock()
            print(floor)
            index=0
            if floor<=ELEVATOR_FLOORS/2:
                index=int(ELEVATOR_FLOORS/2-floor)
            else:
                index=int(30-floor)
            # 将当前楼层按钮的颜色改变
            self.__inner_num_buttons[elevator_id][index].setStyleSheet("background-color : rgb(165,93,81);""border-radius:10px;")
            self.output.append(str(elevator_id) + "号电梯" + "用户需要去" + str(floor) + "楼～")
    
    #处理电梯外部每层楼的按钮点击事件
    def __outer_direction_button_clicked(self, floor, move_state):
        mutex.lock()
        #排除故障电梯
        #先假定所有的电梯都是故障的
        all_fault_flag = True
        for state in elevator_states:
            #然后遍历所有的电梯的状态，只要有一个电梯的状态是正常的，就让all_fault_flag变成False
            if state != ElevatorState.fault:
                all_fault_flag = False

        if all_fault_flag:
            self.output.append("所有电梯均已故障！")
            mutex.unlock()
            return

        task = OuterButtonGenerateTask(floor, move_state)

        if task not in outer_button_events:
            outer_button_events.append(task)

            if move_state == MoveState.up:
                self.__outer_up_buttons[ELEVATOR_FLOORS - floor - 1].setStyleSheet("background-color : yellow")
                self.output.append(str(floor) + "楼的用户有上楼的需求～")

            elif elevator_move_states == MoveState.down:
                self.__outer_down_buttons[ELEVATOR_FLOORS - floor].setStyleSheet("background-color : yellow")
                self.output.append(str(floor) + "楼的用户下楼的需求～")

        mutex.unlock()
    
    #实时更新界面
    def update(self):
        mutex.lock()
        for i in range(ELEVATOR_NUM):
            # 实时更新楼层
            if elevator_states[i] == ElevatorState.going_up:
                self.__floor_displayers[i].display(str(elevator_cur_floor[i]))
                self.close_the_door(i)
            elif elevator_states[i] == ElevatorState.going_down:
                self.__floor_displayers[i].display(str(elevator_cur_floor[i]))
                self.close_the_door(i)
            else:
                self.__floor_displayers[i].display(elevator_cur_floor[i])

            # 实时更新开关门按钮
            if not open_button_clicked[i] and not elevator_states[i] == ElevatorState.fault:
                self.__inner_open_buttons[i].setStyleSheet("background-color :rgb(237,220,195);""border-style: solid;"
                          "border-width: 2px;"
                          "border-color: rgb(165,93,81);"
                          "border-radius:10px;"
                          "color:black;")

            if not close_button_clicked[i] and not elevator_states[i] == ElevatorState.fault:
                self.__inner_close_buttons[i].setStyleSheet("background-color :rgb(237,220,195);""border-style: solid;"
                          "border-width: 2px;"
                          "border-color: rgb(165,93,81);"
                          "border-radius:10px;"
                          "color:black;")

            # 对内部的按钮，如果在开门或关门状态的话，则设进度条
            if elevator_states[i] in [ElevatorState.opening_door, ElevatorState.open_door, ElevatorState.closing_door]:
                index=0
                if elevator_cur_floor[i]<=ELEVATOR_FLOORS/2:
                   index=int(ELEVATOR_FLOORS/2-elevator_cur_floor[i])
                else:
                   index=int(30-elevator_cur_floor[i])
                self.__inner_num_buttons[i][index].setStyleSheet(
                    "background-color : rgb(31," + str(int(59 * (1 - open_progress[i]))) + ",84);"
                          "border-style: solid;"
                          "border-width: 2px;"
                          "border-color: rgb(165,93,81);"
                          "border-radius:10px;"
                          "color:white;")
                # self.open_the_door(i)
            #如果是正在开门，需要调用开门的函数
            if elevator_states[i]==ElevatorState.opening_door:
                self.open_the_door(i,0)
            else:
                self.close_the_door(i)

        mutex.unlock()
        # 对外部来说，遍历任务，找出未完成的设为红色，其他设为默认none
        for button in self.__outer_up_buttons:
            button.setStyleSheet("background-color : None")

        for button in self.__outer_down_buttons:
            button.setStyleSheet("background-color : None")

        mutex.lock()
        #这是一组对于外部上下楼按钮事件的处理
        for outer_task in outer_button_events:
            #如果外部的事件还没有被完全处理好，则将对应的按钮的背景变成红色的
            if outer_task.state != OuterButtonState.finished:
                if outer_task.move_state == MoveState.up:  # 注意index
                    self.__outer_up_buttons[ELEVATOR_FLOORS - outer_task.target - 1].setStyleSheet(
                        "background-color : rgb(165,93,81);")
                elif outer_task.move_state == MoveState.down:
                    self.__outer_down_buttons[ELEVATOR_FLOORS - outer_task.target].setStyleSheet(
                        "background-color : rgb(165,93,81);")

        mutex.unlock()


if __name__ == '__main__':
    app = QApplication(sys.argv)

    # 开启线程
    controller = OuterTaskController()
    controller.start()

    elevators = []
    for i in range(ELEVATOR_NUM):
        elevators.append(Elevator(i))

    for elevator in elevators:
        elevator.start()

    e = ElevatorUi()
    sys.exit(app.exec_())
