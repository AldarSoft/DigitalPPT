import { tw } from "../lib/tailwind-styles";
import fleetMap from '../assets/fleet-map.jpg';
import { CartesianGrid, LabelList, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, } from 'recharts';
const fleetPoints = [
    { x: 19, y: 66, radio: 'A12', team: 'Vehicle 03', location: 'North route' },
    { x: 37, y: 39, radio: 'A07', team: 'Site lead', location: 'East worksite' },
    { x: 55, y: 61, radio: 'A24', team: 'Vehicle 08', location: 'West route' },
    { x: 72, y: 31, radio: 'A19', team: 'Security', location: 'Main entrance' },
    { x: 85, y: 52, radio: 'A31', team: 'Supervisor', location: 'Site office' },
];
function FleetTooltip({ active, payload, }: {
    active?: boolean;
    payload?: Array<{
        payload: {
            radio: string;
            team: string;
            location: string;
        };
    }>;
}) {
    if (!active || !payload?.[0])
        return null;
    const radio = payload[0].payload;
    return <div className={tw("fleet-tooltip")}>
      <strong>Radio {radio.radio} - {radio.team}</strong>
      <span>{radio.location}</span>
      <small>Location visible to authorized fleet</small>
    </div>;
}
export default function FleetVisualization() {
    return (<div className={tw("fleet-chart")} aria-label="Live GPS locations shared between authorized Android radios">
      <img className={tw("fleet-map")} src={fleetMap} alt="" aria-hidden="true"/>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
          <CartesianGrid stroke="#3d5f88" strokeDasharray="2 10" strokeOpacity={0.45}/>
          <XAxis type="number" dataKey="x" domain={[0, 100]} hide/>
          <YAxis type="number" dataKey="y" domain={[0, 100]} hide/>
          <Tooltip content={<FleetTooltip />} cursor={false}/>
          <Scatter data={fleetPoints} fill="#b8ff33">
            <LabelList dataKey="radio" position="top" fill="#d9e8ff" fontSize={11}/>
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>);
}
