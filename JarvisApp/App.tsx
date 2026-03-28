import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  StyleSheet,
  Text,
  View,
  ScrollView,
  TextInput,
  TouchableOpacity,
  Animated,
  Dimensions,
  StatusBar,
  Platform,
  KeyboardAvoidingView,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons, MaterialCommunityIcons, FontAwesome5 } from '@expo/vector-icons';
import { io, Socket } from 'socket.io-client';

// ─── CONFIGURATION ───────────────────────────────
// Change this to your Mac's local IP address
const SERVER_URL = 'https://yummy-carpets-love.loca.lt';

// ─── TYPES ───────────────────────────────────────
interface ChatMessage {
  id: string;
  role: 'user' | 'jarvis' | 'system';
  content: string;
  time: string;
}

interface SysStats {
  cpu: number;
  ram: number;
  battery: number;
  disk: number;
  charging: boolean;
}

type AIState = 'idle' | 'listening' | 'speaking' | 'thinking';

const { width, height } = Dimensions.get('window');

// ─── MAIN APP ────────────────────────────────────
export default function App() {
  const [connected, setConnected] = useState(false);
  const [aiState, setAiState] = useState<AIState>('idle');
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: '0',
      role: 'system',
      content: 'J.A.R.V.I.S initialized. Connect to your Mac to begin.',
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ]);
  const [stats, setStats] = useState<SysStats>({
    cpu: 0, ram: 0, battery: 100, disk: 0, charging: false,
  });
  const [textInput, setTextInput] = useState('');
  const [currentTime, setCurrentTime] = useState('');

  const socketRef = useRef<Socket | null>(null);
  const scrollRef = useRef<ScrollView>(null);

  // Visualizer bars animation
  const vizAnims = useRef(
    Array.from({ length: 20 }, () => new Animated.Value(4))
  ).current;

  // Arc reactor pulse
  const reactorPulse = useRef(new Animated.Value(1)).current;
  const reactorGlow = useRef(new Animated.Value(0.4)).current;

  // ─── GREETING ────────────────────────────────
  const getGreeting = () => {
    const h = new Date().getHours();
    if (h < 12) return 'Good Morning, Master';
    if (h < 17) return 'Good Afternoon, Master';
    return 'Good Evening, Master';
  };

  // ─── CLOCK ───────────────────────────────────
  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setCurrentTime(
        now.toLocaleDateString('en-US', {
          weekday: 'short', month: 'short', day: 'numeric',
        }) + '  •  ' +
        now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      );
    };
    tick();
    const id = setInterval(tick, 30000);
    return () => clearInterval(id);
  }, []);

  // ─── REACTOR ANIMATION ───────────────────────
  useEffect(() => {
    const pulse = Animated.loop(
      Animated.sequence([
        Animated.timing(reactorPulse, {
          toValue: 1.15,
          duration: 1500,
          useNativeDriver: true,
        }),
        Animated.timing(reactorPulse, {
          toValue: 1,
          duration: 1500,
          useNativeDriver: true,
        }),
      ])
    );
    const glow = Animated.loop(
      Animated.sequence([
        Animated.timing(reactorGlow, {
          toValue: 0.8,
          duration: 2000,
          useNativeDriver: true,
        }),
        Animated.timing(reactorGlow, {
          toValue: 0.4,
          duration: 2000,
          useNativeDriver: true,
        }),
      ])
    );
    pulse.start();
    glow.start();
    return () => { pulse.stop(); glow.stop(); };
  }, []);

  // ─── VISUALIZER ANIMATION ────────────────────
  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null;

    if (aiState === 'listening' || aiState === 'speaking') {
      interval = setInterval(() => {
        vizAnims.forEach((anim) => {
          const target = aiState === 'speaking'
            ? Math.random() * 40 + 8
            : Math.random() * 25 + 4;
          Animated.timing(anim, {
            toValue: target,
            duration: aiState === 'speaking' ? 80 : 150,
            useNativeDriver: false,
          }).start();
        });
      }, aiState === 'speaking' ? 80 : 150);
    } else {
      vizAnims.forEach((anim) => {
        Animated.timing(anim, {
          toValue: 4,
          duration: 300,
          useNativeDriver: false,
        }).start();
      });
    }

    return () => { if (interval) clearInterval(interval); };
  }, [aiState]);

  // ─── SOCKET CONNECTION ───────────────────────
  useEffect(() => {
    const socket = io(SERVER_URL, {
      transports: ['websocket'],
      reconnection: true,
      reconnectionDelay: 2000,
    });

    socket.on('connect', () => {
      setConnected(true);
      addMessage('system', 'Connected to J.A.R.V.I.S backend. All systems online.');
    });

    socket.on('disconnect', () => {
      setConnected(false);
      setAiState('idle');
      addMessage('system', 'Connection lost. Attempting to reconnect...');
    });

    socket.on('ai_state', (data: { state: AIState }) => {
      setAiState(data.state);
    });

    socket.on('chat_message', (data: { role: string; content: string }) => {
      addMessage(data.role as ChatMessage['role'], data.content);
    });

    socket.on('sys_stats', (data: SysStats) => {
      setStats(data);
    });

    socketRef.current = socket;
    return () => { socket.disconnect(); };
  }, []);

  // ─── HELPERS ─────────────────────────────────
  const addMessage = useCallback((role: ChatMessage['role'], content: string) => {
    const msg: ChatMessage = {
      id: Date.now().toString() + Math.random().toString(36).slice(2),
      role,
      content,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages((prev) => [...prev, msg]);
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
  }, []);

  const sendCommand = (action: string) => {
    socketRef.current?.emit('control', { action });
  };

  const sendTextCommand = () => {
    if (!textInput.trim()) return;
    socketRef.current?.emit('control', { action: 'text_command', text: textInput.trim() });
    addMessage('user', textInput.trim());
    setTextInput('');
  };

  const quickAction = (action: string) => {
    sendCommand(action);
  };

  // ─── STATUS COLOR ────────────────────────────
  const stateColor = () => {
    switch (aiState) {
      case 'listening': return '#ff3366';
      case 'speaking': return '#00ffcc';
      case 'thinking': return '#ffaa00';
      default: return '#555';
    }
  };

  const stateLabel = () => {
    switch (aiState) {
      case 'listening': return 'LISTENING';
      case 'speaking': return 'SPEAKING';
      case 'thinking': return 'THINKING';
      default: return 'IDLE';
    }
  };

  // ─── STAT BAR COMPONENT ──────────────────────
  const StatBar = ({ label, value, icon, color }: {
    label: string; value: number; icon: string; color: string[];
  }) => (
    <View style={styles.statRow}>
      <View style={styles.statLabel}>
        <MaterialCommunityIcons name={icon as any} size={14} color="#8899aa" />
        <Text style={styles.statText}>{label}</Text>
      </View>
      <View style={styles.statBarOuter}>
        <LinearGradient
          colors={color as any}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 0 }}
          style={[styles.statBarInner, { width: `${Math.min(value, 100)}%` }]}
        />
      </View>
      <Text style={styles.statVal}>{value}%</Text>
    </View>
  );

  // ─── RENDER ──────────────────────────────────
  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#0a0e1a" />
      <LinearGradient colors={['#0a0e1a', '#0f1629', '#0a0e1a']} style={StyleSheet.absoluteFill} />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        {/* ── HEADER ─────────────────────────── */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            {/* Arc Reactor */}
            <Animated.View style={[styles.reactor, { transform: [{ scale: reactorPulse }] }]}>
              <Animated.View style={[styles.reactorGlow, { opacity: reactorGlow }]} />
              <View style={styles.reactorRing1} />
              <View style={styles.reactorRing2} />
              <View style={styles.reactorCore} />
            </Animated.View>
            <View>
              <Text style={styles.brandName}>J.A.R.V.I.S</Text>
              <Text style={styles.brandSub}>{getGreeting()}</Text>
            </View>
          </View>
          <View style={[styles.connBadge, connected && styles.connBadgeOn]}>
            <View style={[styles.connDot, connected && styles.connDotOn]} />
            <Text style={[styles.connText, connected && styles.connTextOn]}>
              {connected ? 'ONLINE' : 'OFFLINE'}
            </Text>
          </View>
        </View>

        {/* ── DATE TIME ──────────────────────── */}
        <Text style={styles.datetime}>{currentTime}</Text>

        {/* ── VISUALIZER ─────────────────────── */}
        <View style={styles.vizWrap}>
          <View style={styles.vizContainer}>
            {vizAnims.map((anim, i) => (
              <Animated.View
                key={i}
                style={[
                  styles.vizBar,
                  {
                    height: anim,
                    backgroundColor: aiState === 'listening'
                      ? '#ff3366'
                      : aiState === 'speaking'
                      ? '#00ffcc'
                      : '#333',
                  },
                ]}
              />
            ))}
          </View>
          <Text style={[styles.vizLabel, { color: stateColor() }]}>{stateLabel()}</Text>
        </View>

        {/* ── SYSTEM STATS ───────────────────── */}
        <View style={styles.statsCard}>
          <StatBar label="CPU" value={stats.cpu} icon="cpu-64-bit" color={['#00ffcc', '#3366ff']} />
          <StatBar label="RAM" value={stats.ram} icon="memory" color={['#ff6633', '#ff3366']} />
          <StatBar label="BAT" value={stats.battery} icon="battery" color={['#33ff66', '#00cc44']} />
          <StatBar label="DSK" value={stats.disk} icon="harddisk" color={['#aa66ff', '#6633ff']} />
        </View>

        {/* ── QUICK ACTIONS ──────────────────── */}
        <View style={styles.quickRow}>
          <TouchableOpacity style={styles.quickBtn} onPress={() => quickAction('weather')}>
            <Ionicons name="cloud-outline" size={18} color="#00ffcc" />
            <Text style={styles.quickText}>Weather</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickBtn} onPress={() => quickAction('news')}>
            <Ionicons name="newspaper-outline" size={18} color="#00ffcc" />
            <Text style={styles.quickText}>News</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickBtn} onPress={() => quickAction('joke')}>
            <Ionicons name="happy-outline" size={18} color="#00ffcc" />
            <Text style={styles.quickText}>Joke</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickBtn} onPress={() => quickAction('system_status')}>
            <Ionicons name="hardware-chip-outline" size={18} color="#00ffcc" />
            <Text style={styles.quickText}>Status</Text>
          </TouchableOpacity>
        </View>

        {/* ── CHAT AREA ──────────────────────── */}
        <View style={styles.chatArea}>
          <ScrollView
            ref={scrollRef}
            style={styles.chatScroll}
            contentContainerStyle={styles.chatContent}
            showsVerticalScrollIndicator={false}
            onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
          >
            {messages.map((msg) => (
              <View
                key={msg.id}
                style={[
                  styles.msgRow,
                  msg.role === 'user' && styles.msgRowUser,
                ]}
              >
                {msg.role !== 'user' && (
                  <View style={[
                    styles.msgAvatar,
                    msg.role === 'jarvis' ? styles.avatarJarvis : styles.avatarSystem,
                  ]}>
                    <Ionicons
                      name={msg.role === 'jarvis' ? 'hardware-chip' : 'terminal'}
                      size={14}
                      color={msg.role === 'jarvis' ? '#00ffcc' : '#8899aa'}
                    />
                  </View>
                )}
                <View style={[
                  styles.msgBubble,
                  msg.role === 'user' ? styles.bubbleUser
                    : msg.role === 'jarvis' ? styles.bubbleJarvis
                    : styles.bubbleSystem,
                ]}>
                  <Text style={[
                    styles.msgSender,
                    msg.role === 'user' && styles.msgSenderUser,
                  ]}>
                    {msg.role === 'user' ? 'You' : msg.role === 'jarvis' ? 'Jarvis' : 'System'}
                  </Text>
                  <Text style={styles.msgContent}>{msg.content}</Text>
                  <Text style={styles.msgTime}>{msg.time}</Text>
                </View>
                {msg.role === 'user' && (
                  <View style={[styles.msgAvatar, styles.avatarUser]}>
                    <Ionicons name="person" size={14} color="#3366ff" />
                  </View>
                )}
              </View>
            ))}
          </ScrollView>
        </View>

        {/* ── BOTTOM CONTROLS ────────────────── */}
        <View style={styles.bottomBar}>
          <View style={styles.inputRow}>
            <TextInput
              style={styles.input}
              placeholder="Type a command..."
              placeholderTextColor="#556"
              value={textInput}
              onChangeText={setTextInput}
              onSubmitEditing={sendTextCommand}
              returnKeyType="send"
            />
            <TouchableOpacity style={styles.sendBtn} onPress={sendTextCommand}>
              <Ionicons name="send" size={18} color="#0a0e1a" />
            </TouchableOpacity>
          </View>

          <View style={styles.controlRow}>
            <TouchableOpacity
              style={[styles.ctrlBtn, styles.wakeBtn]}
              onPress={() => sendCommand('wake')}
              activeOpacity={0.7}
            >
              <Ionicons name="mic" size={22} color="#0a0e1a" />
              <Text style={styles.ctrlBtnText}>WAKE</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.ctrlBtn, styles.haltBtn]}
              onPress={() => sendCommand('stop')}
              activeOpacity={0.7}
            >
              <Ionicons name="stop-circle" size={22} color="#fff" />
              <Text style={[styles.ctrlBtnText, { color: '#fff' }]}>HALT</Text>
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

// ─── STYLES ──────────────────────────────────────
const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0a0e1a',
  },

  // Header
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: Platform.OS === 'ios' ? 60 : 40,
    paddingBottom: 8,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  reactor: {
    width: 44,
    height: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  reactorGlow: {
    position: 'absolute',
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#00ffcc',
  },
  reactorRing1: {
    position: 'absolute',
    width: 38,
    height: 38,
    borderRadius: 19,
    borderWidth: 2,
    borderColor: '#00ddaa',
  },
  reactorRing2: {
    position: 'absolute',
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: '#00ffcc88',
  },
  reactorCore: {
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: '#00ffcc',
    shadowColor: '#00ffcc',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 8,
  },
  brandName: {
    color: '#fff',
    fontSize: 22,
    fontWeight: '800',
    letterSpacing: 3,
  },
  brandSub: {
    color: '#8899aa',
    fontSize: 12,
    fontWeight: '400',
    marginTop: 1,
  },

  // Connection badge
  connBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 20,
    backgroundColor: 'rgba(255,50,50,0.1)',
    borderWidth: 1,
    borderColor: 'rgba(255,50,50,0.3)',
  },
  connBadgeOn: {
    backgroundColor: 'rgba(0,255,204,0.1)',
    borderColor: 'rgba(0,255,204,0.3)',
  },
  connDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: '#ff3333',
  },
  connDotOn: {
    backgroundColor: '#00ffcc',
    shadowColor: '#00ffcc',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 4,
  },
  connText: {
    color: '#ff5555',
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 1,
  },
  connTextOn: {
    color: '#00ffcc',
  },

  // DateTime
  datetime: {
    color: '#556',
    fontSize: 12,
    textAlign: 'center',
    marginTop: 4,
    letterSpacing: 1,
    fontWeight: '500',
  },

  // Visualizer
  vizWrap: {
    alignItems: 'center',
    marginVertical: 10,
  },
  vizContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    height: 50,
    justifyContent: 'center',
  },
  vizBar: {
    width: 4,
    borderRadius: 2,
  },
  vizLabel: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 3,
    marginTop: 6,
  },

  // Stats Card
  statsCard: {
    marginHorizontal: 16,
    backgroundColor: 'rgba(255,255,255,0.03)',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.06)',
    gap: 10,
  },
  statRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  statLabel: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    width: 55,
  },
  statText: {
    color: '#8899aa',
    fontSize: 11,
    fontWeight: '600',
  },
  statBarOuter: {
    flex: 1,
    height: 6,
    borderRadius: 3,
    backgroundColor: 'rgba(255,255,255,0.06)',
    overflow: 'hidden',
  },
  statBarInner: {
    height: '100%',
    borderRadius: 3,
  },
  statVal: {
    color: '#aabbcc',
    fontSize: 11,
    fontWeight: '600',
    width: 36,
    textAlign: 'right',
    fontVariant: ['tabular-nums'],
  },

  // Quick Actions
  quickRow: {
    flexDirection: 'row',
    marginHorizontal: 16,
    marginTop: 10,
    gap: 8,
  },
  quickBtn: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    backgroundColor: 'rgba(0,255,204,0.04)',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: 'rgba(0,255,204,0.1)',
    gap: 4,
  },
  quickText: {
    color: '#8899aa',
    fontSize: 10,
    fontWeight: '600',
  },

  // Chat Area
  chatArea: {
    flex: 1,
    marginTop: 10,
    marginHorizontal: 16,
  },
  chatScroll: {
    flex: 1,
  },
  chatContent: {
    paddingBottom: 10,
    gap: 10,
  },
  msgRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 8,
  },
  msgRowUser: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
  },
  msgAvatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 2,
  },
  avatarJarvis: {
    backgroundColor: 'rgba(0,255,204,0.1)',
    borderWidth: 1,
    borderColor: 'rgba(0,255,204,0.2)',
  },
  avatarSystem: {
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
  },
  avatarUser: {
    backgroundColor: 'rgba(51,102,255,0.1)',
    borderWidth: 1,
    borderColor: 'rgba(51,102,255,0.2)',
  },
  msgBubble: {
    maxWidth: '75%',
    padding: 12,
    borderRadius: 14,
  },
  bubbleUser: {
    backgroundColor: 'rgba(51,102,255,0.12)',
    borderWidth: 1,
    borderColor: 'rgba(51,102,255,0.2)',
    borderBottomRightRadius: 4,
  },
  bubbleJarvis: {
    backgroundColor: 'rgba(0,255,204,0.06)',
    borderWidth: 1,
    borderColor: 'rgba(0,255,204,0.12)',
    borderBottomLeftRadius: 4,
  },
  bubbleSystem: {
    backgroundColor: 'rgba(255,255,255,0.03)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.06)',
    borderBottomLeftRadius: 4,
  },
  msgSender: {
    color: '#00ffcc',
    fontSize: 11,
    fontWeight: '700',
    marginBottom: 3,
    letterSpacing: 0.5,
  },
  msgSenderUser: {
    color: '#6699ff',
    textAlign: 'right',
  },
  msgContent: {
    color: '#dde4ee',
    fontSize: 14,
    lineHeight: 20,
  },
  msgTime: {
    color: '#445',
    fontSize: 10,
    marginTop: 4,
    textAlign: 'right',
  },

  // Bottom Bar
  bottomBar: {
    paddingHorizontal: 16,
    paddingBottom: Platform.OS === 'ios' ? 30 : 16,
    paddingTop: 10,
    gap: 10,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  input: {
    flex: 1,
    height: 46,
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderRadius: 12,
    paddingHorizontal: 16,
    color: '#fff',
    fontSize: 14,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
  },
  sendBtn: {
    width: 46,
    height: 46,
    borderRadius: 12,
    backgroundColor: '#00ffcc',
    justifyContent: 'center',
    alignItems: 'center',
  },
  controlRow: {
    flexDirection: 'row',
    gap: 12,
  },
  ctrlBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 14,
    borderRadius: 12,
  },
  wakeBtn: {
    backgroundColor: '#00ffcc',
  },
  haltBtn: {
    backgroundColor: '#ff3366',
  },
  ctrlBtnText: {
    fontSize: 14,
    fontWeight: '800',
    letterSpacing: 2,
    color: '#0a0e1a',
  },
});
