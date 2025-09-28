import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
// Os imports do Leaflet foram removidos, pois ele agora é carregado pelo index.html

function App() {
  // --- Estados do Componente ---
  const [linha, setLinha] = useState('');
  const [onibus, setOnibus] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [mapCenter] = useState([-22.9068, -43.1729]); // Rio de Janeiro

  // Estados para o formulário de alerta
  const [pontoPartida, setPontoPartida] = useState(null);
  const [email, setEmail] = useState('');
  const [alertaStatus, setAlertaStatus] = useState({ visivel: false, mensagem: '', sucesso: false });

  // --- Refs para o Mapa Manual ---
  const mapContainerRef = useRef(null); // Ref para a <div> que vai conter o mapa
  const mapRef = useRef(null);          // Ref para guardar a instância do mapa
  const busMarkersRef = useRef([]);     // Ref para guardar os marcadores dos ônibus
  const startPointMarkerRef = useRef(null); // Ref para o marcador do ponto de partida

  // --- Efeito para Inicializar o Mapa ---
  useEffect(() => {
    if (mapRef.current) return; // Se o mapa já foi criado, não faz nada

    const intervalId = setInterval(() => {
      if (window.L && window.L.map && mapContainerRef.current) {
        clearInterval(intervalId); 

        const map = window.L.map(mapContainerRef.current).setView(mapCenter, 12);
        window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(map);

        map.on('click', (e) => {
          setPontoPartida(e.latlng);
        });
        
        mapRef.current = map;
      }
    }, 100); 

    return () => clearInterval(intervalId);
  }, [mapCenter]);


  // --- Efeito para Atualizar os Marcadores dos Ônibus ---
  useEffect(() => {
    if (!mapRef.current) return; 

    busMarkersRef.current.forEach(marker => marker.remove());
    busMarkersRef.current = [];

    const busIcon = window.L.icon({
      iconUrl: 'https://cdn-icons-png.flaticon.com/512/3448/3448624.png',
      iconSize: [35, 35], iconAnchor: [17, 35], popupAnchor: [0, -35],
    });

    onibus.forEach(bus => {
      const marker = window.L.marker([bus.latitude, bus.longitude], { icon: busIcon })
        .addTo(mapRef.current)
        .bindPopup(`<b>Ônibus:</b> ${bus.ordem}<br/><b>Velocidade:</b> ${Math.round(bus.velocidade)} km/h`);
      busMarkersRef.current.push(marker);
    });

  }, [onibus]); 


  // --- Efeito para Atualizar o Marcador do Ponto de Partida ---
  useEffect(() => {
    if (!mapRef.current) return;

    if (startPointMarkerRef.current) {
      startPointMarkerRef.current.remove();
      startPointMarkerRef.current = null;
    }

    if (pontoPartida) {
      const startPointIcon = window.L.icon({
        iconUrl: 'https://cdn-icons-png.flaticon.com/512/684/684908.png',
        iconSize: [40, 40], iconAnchor: [20, 40], popupAnchor: [0, -40],
      });
      
      startPointMarkerRef.current = window.L.marker([pontoPartida.lat, pontoPartida.lng], { icon: startPointIcon })
        .addTo(mapRef.current)
        .bindPopup('Seu ponto de partida.');
    }
  }, [pontoPartida]); 

  // --- Lógica de busca e alerta ---
  const buscarOnibus = useCallback(async (linhaAtual) => {
    if (!linhaAtual) return; setLoading(true); setError(null);
    try {
      const response = await axios.get(`http://localhost:8000/api/v1/posicoes/${linhaAtual}`);
      if (response.data && response.data.length > 0) { setOnibus(response.data); }
      else { setOnibus([]); setError('Nenhum ônibus encontrado para esta linha no momento.'); }
    } catch (err) { console.error("Erro ao buscar dados:", err); setError('Falha ao buscar dados.'); }
    finally { setLoading(false); }
  }, []);

  const handleFormSubmit = (e) => { e.preventDefault(); buscarOnibus(linha); };

  useEffect(() => {
    if (!linha) return;
    const intervalId = setInterval(() => { buscarOnibus(linha); }, 30000);
    return () => clearInterval(intervalId);
  }, [linha, buscarOnibus]);

  const handleCriarAlerta = async (e) => {
    e.preventDefault();
    if (!email || !pontoPartida || !linha) {
      setAlertaStatus({ visivel: true, mensagem: 'Preencha tudo e clique no mapa para definir o ponto.', sucesso: false });
      return;
    }
    const dadosAlerta = { email, linha, latitude_ponto: pontoPartida.lat, longitude_ponto: pontoPartida.lng };
    try {
      const response = await axios.post('http://localhost:8000/api/v1/alertas', dadosAlerta);
      if (response.data.status === 'sucesso') {
        setAlertaStatus({ visivel: true, mensagem: 'Alerta criado com sucesso!', sucesso: true });
        setEmail(''); setPontoPartida(null);
      }
    } catch (err) {
      setAlertaStatus({ visivel: true, mensagem: 'Falha ao criar o alerta.', sucesso: false });
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-100 font-sans">
      <header className="bg-slate-800 text-white p-4 shadow-md">
        <h1 className="text-2xl font-bold text-center">🚌 Alerta de Ônibus - Rio de Janeiro</h1>
      </header>
      <main className="flex-grow flex flex-col md:flex-row-reverse overflow-hidden">
        <div className="w-full md:w-2/3 h-64 md:h-full bg-gray-300" ref={mapContainerRef} style={{minHeight: '200px'}}>
          {/* O mapa Leaflet será inserido aqui pelo useEffect */}
        </div>
        <div className="w-full md:w-1/3 p-4 overflow-y-auto bg-white shadow-lg">
          <div className="mb-8 p-4 border rounded-lg bg-gray-50">
            <h2 className="text-xl font-semibold mb-2 text-gray-800">1. Buscar Linha</h2>
            <form onSubmit={handleFormSubmit}>
              <div className="flex items-center">
                <input type="text" value={linha} onChange={(e) => setLinha(e.target.value)} placeholder="Ex: 483" className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 focus:outline-none focus:shadow-outline"/>
                <button type="submit" disabled={loading} className="ml-2 bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline disabled:bg-blue-300">
                  {loading ? '...' : 'Buscar'}
                </button>
              </div>
            </form>
          </div>
          <div className="mb-6 p-4 border rounded-lg bg-gray-50">
            <h2 className="text-xl font-semibold mb-2 text-gray-800">2. Criar Alerta</h2>
            <p className="text-sm text-gray-600 mb-4">Após buscar a linha, clique no mapa para definir seu ponto de partida e preencha seu e-mail.</p>
            <form onSubmit={handleCriarAlerta}>
              <div className="mb-4">
                <label className="block text-gray-700 text-sm font-bold mb-2" htmlFor="email">Seu E-mail:</label>
                <input type="email" id="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="seu.email@exemplo.com" className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 focus:outline-none focus:shadow-outline"/>
              </div>
              <div className="mb-4">
                <label className="block text-gray-700 text-sm font-bold mb-2">Ponto de Partida:</label>
                <div className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-500 bg-gray-200">
                  {pontoPartida ? `Lat: ${pontoPartida.lat.toFixed(4)}, Lng: ${pontoPartida.lng.toFixed(4)}` : 'Clique no mapa para definir'}
                </div>
              </div>
              <button type="submit" className="w-full bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline">
                Cadastrar Alerta
              </button>
            </form>
            {alertaStatus.visivel && (
              <div className={`mt-4 p-3 rounded text-center ${alertaStatus.sucesso ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                {alertaStatus.mensagem}
              </div>
            )}
          </div>
          <div className="overflow-x-auto">
            <h2 className="text-xl font-semibold mb-2 text-gray-800">Ônibus em Circulação</h2>
            {error && <div className="text-red-500 text-center p-2">{error}</div>}
            <table className="min-w-full bg-white">
              <thead className="bg-gray-800 text-white">
                <tr>
                  <th className="text-left py-3 px-4 uppercase font-semibold text-sm">Ordem</th>
                  <th className="text-left py-3 px-4 uppercase font-semibold text-sm">Velocidade</th>
                  <th className="text-left py-3 px-4 uppercase font-semibold text-sm">Atualização</th>
                </tr>
              </thead>
              <tbody className="text-gray-700">
                {onibus.length > 0 ? (
                  onibus.map(bus => (
                    <tr key={bus.ordem} className="hover:bg-gray-100 border-b">
                      <td className="py-3 px-4">{bus.ordem}</td>
                      <td className="py-3 px-4">{Math.round(bus.velocidade)} km/h</td>
                      <td className="py-3 px-4">
                        {bus.hora_atualizacao}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr><td colSpan="3" className="text-center py-4">{loading ? 'Carregando...' : 'Nenhum ônibus para exibir.'}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;

